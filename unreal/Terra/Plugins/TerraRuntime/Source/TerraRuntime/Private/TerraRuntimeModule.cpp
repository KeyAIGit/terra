#include "TerraRuntimeModule.h"

#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY(LogTerraRuntime);

void FTerraRuntimeModule::StartupModule()
{
    UE_LOG(LogTerraRuntime, Log, TEXT("Terra Runtime initialized."));
}

void FTerraRuntimeModule::ShutdownModule()
{
}

IMPLEMENT_MODULE(FTerraRuntimeModule, TerraRuntime)
