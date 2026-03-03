# -*- coding: utf-8 -*-
"""Extensions router: /v1/extensions/* endpoints."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends

from app.adapters.infrastructure.api_models import (
    InstallPackageRequest,
    InstallPackageResponse,
    PackageStatusResponse,
    PrewarmResponse,
    User,
)

logger = logging.getLogger(__name__)


def create_extensions_router(extension_manager, get_current_user) -> APIRouter:
    """
    Create the extensions router.

    Args:
        extension_manager: ExtensionManager for package installation
        get_current_user: Dependency callable for authentication

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.post("/v1/extensions/install", response_model=InstallPackageResponse)
    async def install_package(
        request: InstallPackageRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
    ) -> InstallPackageResponse:
        """Install a package using uv in the background (Protected endpoint)."""
        try:
            package_name = request.package_name.lower()
            logger.info(f"User '{current_user.username}' requesting installation: {package_name}")

            if extension_manager.is_package_installed(package_name):
                return InstallPackageResponse(
                    success=True,
                    message=f"Package '{package_name}' is already installed",
                    package_name=package_name,
                    already_installed=True,
                )

            background_tasks.add_task(extension_manager.install_package, package_name)
            return InstallPackageResponse(
                success=True,
                message=f"Installation of '{package_name}' started in background",
                package_name=package_name,
                already_installed=False,
            )
        except Exception as e:
            logger.error(f"Error installing package: {e}", exc_info=True)
            raise

    @router.get("/v1/extensions/status/{package_name}", response_model=PackageStatusResponse)
    async def get_package_status(
        package_name: str,
        current_user: User = Depends(get_current_user),
    ) -> PackageStatusResponse:
        """Check whether a package is installed (Protected endpoint)."""
        try:
            package_name = package_name.lower()
            installed = extension_manager.is_package_installed(package_name)
            return PackageStatusResponse(package_name=package_name, installed=installed)
        except Exception as e:
            logger.error(f"Error checking package status: {e}", exc_info=True)
            raise

    @router.post("/v1/extensions/prewarm", response_model=PrewarmResponse)
    async def prewarm_libraries(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
    ) -> PrewarmResponse:
        """Pre-warm recommended libraries (pandas, numpy, matplotlib) in the background."""
        try:
            logger.info(f"User '{current_user.username}' requesting pre-warming")
            missing_libs = [
                lib
                for lib in extension_manager.RECOMMENDED_LIBRARIES
                if not extension_manager.is_package_installed(lib)
            ]

            if not missing_libs:
                return PrewarmResponse(
                    message="All recommended libraries are already installed",
                    libraries={lib: True for lib in extension_manager.RECOMMENDED_LIBRARIES},
                    all_installed=True,
                )

            background_tasks.add_task(extension_manager.ensure_recommended_libraries)
            status = {
                lib: extension_manager.is_package_installed(lib)
                for lib in extension_manager.RECOMMENDED_LIBRARIES
            }
            return PrewarmResponse(
                message=f"Pre-warming started in background for: {', '.join(missing_libs)}",
                libraries=status,
                all_installed=False,
            )
        except Exception as e:
            logger.error(f"Error in pre-warming endpoint: {e}", exc_info=True)
            raise

    return router
