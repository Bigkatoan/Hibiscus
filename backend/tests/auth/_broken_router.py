"""Fixture module for test_app_mounts_extra_routers: imports a dependency that does not exist."""

import nonexistent_dependency_for_hibiscus_tests  # type: ignore[import-not-found]  # noqa: F401
