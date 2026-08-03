#include "TerraRealitySliceGameMode.h"

#include "Engine/World.h"
#include "GameFramework/PlayerStart.h"
#include "TerraRealitySliceEnvironment.h"
#include "TerraRealitySliceHUD.h"
#include "TerraRuntimeModule.h"

namespace TerraRealitySliceGameMode
{
const FName PlayerStartTag(TEXT("TerraRealitySliceStart"));
}

ATerraRealitySliceGameMode::ATerraRealitySliceGameMode()
{
    bStartPlayersAsSpectators = false;
    HUDClass = ATerraRealitySliceHUD::StaticClass();
}

void ATerraRealitySliceGameMode::InitGame(
    const FString& MapName,
    const FString& Options,
    FString& ErrorMessage
)
{
    Super::InitGame(MapName, Options, ErrorMessage);

    if (!UTerraRealitySliceLayoutLibrary::LoadBestAvailableLayout(LoadedLayout, LoadDiagnostic))
    {
        ErrorMessage = LoadDiagnostic;
        UE_LOG(LogTerraRuntime, Error, TEXT("Reality slice load failed: %s"), *ErrorMessage);
        return;
    }

    UWorld* World = GetWorld();
    if (!World)
    {
        ErrorMessage = TEXT("Terra reality slice could not acquire a world.");
        return;
    }

    FActorSpawnParameters SpawnParameters;
    SpawnParameters.Owner = this;
    SpawnParameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    SpawnParameters.ObjectFlags |= RF_Transient;

    RealitySliceEnvironment = World->SpawnActor<ATerraRealitySliceEnvironment>(
        ATerraRealitySliceEnvironment::StaticClass(),
        FTransform::Identity,
        SpawnParameters
    );
    if (!RealitySliceEnvironment)
    {
        ErrorMessage = TEXT("Terra reality slice failed to spawn its procedural environment.");
        return;
    }

    FString BuildError;
    if (!RealitySliceEnvironment->BuildFromLayout(LoadedLayout, BuildError))
    {
        ErrorMessage = FString::Printf(TEXT("Terra reality-slice environment rejected the layout: %s"), *BuildError);
        UE_LOG(LogTerraRuntime, Error, TEXT("%s"), *ErrorMessage);
        return;
    }

    const FTransform StartTransform(
        FRotator(0.0F, LoadedLayout.PlayerStart.YawDeg, 0.0F),
        LoadedLayout.PlayerStart.LocationCm
    );
    RealitySlicePlayerStart = World->SpawnActor<APlayerStart>(
        APlayerStart::StaticClass(),
        StartTransform,
        SpawnParameters
    );
    if (!RealitySlicePlayerStart)
    {
        ErrorMessage = TEXT("Terra reality slice failed to spawn its validated PlayerStart.");
        return;
    }
    RealitySlicePlayerStart->Tags.AddUnique(TerraRealitySliceGameMode::PlayerStartTag);

    UE_LOG(LogTerraRuntime, Display, TEXT("%s"), *LoadDiagnostic);
    UE_LOG(LogTerraRuntime, Display, TEXT("Reality-slice spawn audit: %s"), *LoadedLayout.PlayerStartDiagnostic);
    UE_LOG(
        LogTerraRuntime,
        Display,
        TEXT("Reality-slice environment ready: source=%d rendered=%d gate_piers=%d gate_opening=%.0fcm datum=flat-z0."),
        RealitySliceEnvironment->GetSourceElementCount(),
        RealitySliceEnvironment->GetRenderedInstanceCount(),
        RealitySliceEnvironment->GetGateCollisionPierCount(),
        RealitySliceEnvironment->GetGateOpeningWidthCm()
    );
}

void ATerraRealitySliceGameMode::StartPlay()
{
    Super::StartPlay();
    UE_LOG(
        LogTerraRuntime,
        Display,
        TEXT("TERRA ground-level ward started: STATUS=SPATIAL PROTOTYPE/BLOCKOUT. It validates spatial interaction, not photoreal or reality-level simulation fidelity.")
    );
}

AActor* ATerraRealitySliceGameMode::ChoosePlayerStart_Implementation(AController* Player)
{
    if (IsValid(RealitySlicePlayerStart))
    {
        return RealitySlicePlayerStart;
    }
    return Super::ChoosePlayerStart_Implementation(Player);
}
