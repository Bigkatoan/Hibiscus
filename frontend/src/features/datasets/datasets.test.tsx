import { File as NodeFile, Blob as NodeBlob } from "node:buffer";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { readBlob } from "@/features/upload/hashing";
import { fetchTransport, type PartTransport } from "@/features/upload/uploader";
import { UploadPage } from "@/features/upload/UploadPage";
import { WorkspaceProvider } from "@/features/workspace/context";
import { fakeUploadServer } from "@/test/fakeUploadServer";
import * as f from "@/test/fixtures";
import { renderApp, renderRoute } from "@/test/render";
import { http, problemResponse, server } from "@/test/server";

describe("datasets", () => {
  it("lists datasets with latest version status and links to detail", async () => {
    renderApp("/w/robot-lab/datasets");
    const link = await screen.findByRole("link", { name: "so101 pick and place" });
    expect(link).toHaveAttribute("href", `/w/robot-lab/datasets/${f.IDS.dataset}`);
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("11,277")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Upload dataset/ })).toBeInTheDocument();
  });

  it("hides write actions for viewers", async () => {
    renderApp("/w/side-project/datasets");
    await screen.findByRole("link", { name: "so101 pick and place" });
    expect(screen.queryByRole("link", { name: /Upload dataset/ })).not.toBeInTheDocument();
  });

  it("searches by name (q param)", async () => {
    const queries: string[] = [];
    server.use(
      http.get("/datasets", ({ request }) => {
        queries.push(new URL(request.url).searchParams.get("q") ?? "");
        return HttpResponse.json({ items: [f.dataset], next_cursor: null });
      }),
    );
    renderApp("/w/robot-lab/datasets");
    const user = userEvent.setup();
    await user.type(await screen.findByRole("searchbox"), "so101");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => {
      expect(queries).toContain("so101");
    });
  });

  it("imports from the Hub", async () => {
    let body: unknown = null;
    server.use(
      http.post("/datasets/import-hf", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { dataset: f.dataset, version: f.versionSummary, job: f.job },
          { status: 202 },
        );
      }),
    );
    const { router } = renderApp("/w/robot-lab/datasets");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Import from Hugging Face/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Hub URI/), "hf://lerobot/svla_so101_pickplace@main");
    await user.click(within(dialog).getByRole("button", { name: "Start import" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/robot-lab/datasets/${f.IDS.dataset}`);
    });
    expect(body).toEqual({
      workspace_id: f.IDS.ws,
      hf_uri: "hf://lerobot/svla_so101_pickplace@main",
      new_dataset_name: "svla_so101_pickplace",
    });
  });

  it("shows version overview, validation issues by code, and the episode viewer", async () => {
    renderApp(`/w/robot-lab/datasets/${f.IDS.dataset}`);
    expect(await screen.findByRole("heading", { name: "so101 pick and place" })).toBeInTheDocument();
    expect((await screen.findAllByText("observation.images.wrist_cam")).length).toBeGreaterThan(0);
    expect(screen.getByText("shoulder_pan.pos")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Validation" }));
    expect(await screen.findByText("Timestamps are irregular in episode 3.")).toBeInTheDocument();
    expect(screen.getByText("Passed with warnings")).toBeInTheDocument();
    expect(screen.getByText("0 errors, 1 warnings")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Episodes" }));
    const video = await waitFor(() => {
      const v = document.querySelector("video");
      if (!v) throw new Error("no video");
      return v;
    });
    expect(video.getAttribute("src")).toBe(
      `${window.location.origin}/api/v1/dataset-versions/${f.IDS.version}/media/previews/observation.images.wrist_cam/episode_000000.mp4`,
    );
    expect(await screen.findByText("observation.state over time")).toBeInTheDocument();
    expect(screen.getByText("action over time")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /First frame of episode/ })).toHaveLength(3);
  });

  it("falls back when no H.264 preview exists for an AV1 original", async () => {
    server.use(
      http.get("/dataset-versions/{version_id}/episodes/{episode_index}", () =>
        HttpResponse.json({
          ...f.episode,
          videos: f.episode.videos.map((v) => ({ ...v, preview_media_path: null })),
        }),
      ),
    );
    renderApp(`/w/robot-lab/datasets/${f.IDS.dataset}?tab=episodes`);
    expect(await screen.findByText("No browser preview for this av1 video yet.")).toBeInTheDocument();
  });

  it("re-runs validation and shows the job", async () => {
    server.use(
      http.post("/dataset-versions/{version_id}/validation", () =>
        HttpResponse.json({ ...f.job, status: "running", progress: 0.5 }, { status: 202 }),
      ),
      http.get("/jobs/{job_id}", () => HttpResponse.json({ ...f.job, status: "succeeded", progress: 1 })),
    );
    renderApp(`/w/robot-lab/datasets/${f.IDS.dataset}?tab=validation`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Run validation again/ }));
    expect(await screen.findByText("Succeeded")).toBeInTheDocument();
  });

  it("shows a not-found page for an unknown workspace slug", async () => {
    renderApp("/w/nope/datasets");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });

  it("maps 404 on a dataset to a localised message", async () => {
    server.use(http.get("/datasets/{dataset_id}", () => problemResponse(404, "not_found")));
    renderApp(`/w/robot-lab/datasets/${f.IDS.dataset}`);
    expect(await screen.findByText("Not found, or you do not have access.")).toBeInTheDocument();
  });
});

describe("upload page", () => {
  // jsdom Blobs are converted to Node Blobs before hitting the (Node) fetch stack in tests.
  const nodeTransport: PartTransport = async (url, body, headers, onProgress, signal) =>
    fetchTransport(url, new NodeBlob([await readBlob(body)]) as unknown as Blob, headers, onProgress, signal);

  it("hashes, uploads in parts and offers 'Train now'", async () => {
    const bytes = new Uint8Array(2500).map((_, i) => i % 251);
    const fake = fakeUploadServer(bytes, { partSize: 1000 });
    server.use(...fake.handlers);
    renderRoute(
      <WorkspaceProvider value={f.membership}>
        <UploadPage
          uploaderOptions={{ transport: nodeTransport, sleep: () => Promise.resolve(), cacheHashes: false }}
        />
      </WorkspaceProvider>,
    );
    const input = await screen.findByLabelText("Choose archive");
    const file = new NodeFile([bytes], "Picknplace_20261114.rar", { lastModified: 1 }) as unknown as File;
    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByDisplayValue("Picknplace_20261114")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Start upload/ }));
    const train = await screen.findByRole("link", { name: /Train now/ }, { timeout: 10_000 });
    expect(train).toHaveAttribute("href", `/w/robot-lab/runs/new?version=${f.IDS.version}`);
    expect(fake.store.size).toBe(3);
  });

  it("rejects unsupported archive formats before upload", async () => {
    renderRoute(
      <WorkspaceProvider value={f.membership}>
        <UploadPage />
      </WorkspaceProvider>,
    );
    const input = await screen.findByLabelText("Choose archive");
    fireEvent.change(input, { target: { files: [new File(["x"], "data.7z")] } });
    expect(await screen.findByText("Unsupported archive format.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start upload/ })).toBeDisabled();
  });
});
