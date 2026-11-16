# Hibiscus Station

Hibiscus Station, the app that runs on the computer the robot is plugged into (connect and
calibrate the arms, cameras, teleoperation, dataset recording, upload, pulling a trained model and
running it with motor telemetry and thermal auto-stop, plus trajectories, block programs and a 3D
twin), now lives in its own repository:

**<https://github.com/Bigkatoan/hibiscus-station>**

Its user guide, hardware acceptance checklist, specification and install instructions are there.

From this server's side nothing changes: Station uploads datasets through the same resumable upload
as `hibiscus push` ([Datasets](02-datasets.md)), pulls model bundles like `hibiscus pull`
([Running on the robot](06-run-on-robot.md)) and authenticates with a personal access token. Once
Station is installed, `hibiscus station …` launches it ([CLI](03-cli.md)).
