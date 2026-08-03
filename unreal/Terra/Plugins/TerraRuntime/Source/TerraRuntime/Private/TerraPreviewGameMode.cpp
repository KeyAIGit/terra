#include "TerraPreviewGameMode.h"

#include "Engine/World.h"
#include "GameFramework/PlayerStart.h"
#include "TerraPreviewEnvironment.h"
#include "TerraRuntimeModule.h"

namespace TerraPreview
{
const FName PreviewStartTag(TEXT("TerraPreviewStart"));
}

ATerraPreviewGameMode::ATerraPreviewGameMode()
{
    bStartPlayersAsSpectators = false;
}

FTransform ATerraPreviewGameMode::GetPreviewStartTransform()
{
    // Terra's capsule half-height is 96 cm. Starting at 120 cm gives a safe
    // 24 cm air gap before CharacterMovement settles onto the test pad.
    return FTransform(FRotator::ZeroRotator, FVector(0.0F, 0.0F, 120.0F));
}

void ATerraPreviewGameMode::InitGame(
    const FString& MapName,
    const FString& Options,
    FString& ErrorMessage
)
{
    Super::InitGame(MapName, Options, ErrorMessage);

    UWorld* World = GetWorld();
    if (!World)
    {
        ErrorMessage = TEXT("Terra preview could not acquire a world.");
        return;
    }

    FActorSpawnParameters SpawnParameters;
    SpawnParameters.Owner = this;
    SpawnParameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    SpawnParameters.ObjectFlags |= RF_Transient;

    PreviewEnvironment = World->SpawnActor<ATerraPreviewEnvironment>(
        ATerraPreviewEnvironment::StaticClass(),
        FTransform::Identity,
        SpawnParameters
    );

    PreviewPlayerStart = World->SpawnActor<APlayerStart>(
        APlayerStart::StaticClass(),
        GetPreviewStartTransform(),
        SpawnParameters
    );
    if (PreviewPlayerStart)
    {
        PreviewPlayerStart->Tags.AddUnique(TerraPreview::PreviewStartTag);
    }

    if (!PreviewEnvironment || !PreviewPlayerStart)
    {
        ErrorMessage = TEXT("Terra preview failed to create its collision test pad or PlayerStart.");
        UE_LOG(LogTerraRuntime, Error, TEXT("%s"), *ErrorMessage);
    }
}

void ATerraPreviewGameMode::StartPlay()
{
    Super::StartPlay();
    UE_LOG(
        LogTerraRuntime,
        Display,
        TEXT("TERRA preview started: STATUS=BLOCKOUT. This runtime test pad validates camera, input and collision; it is not final simulation content.")
    );
}

AActor* ATerraPreviewGameMode::ChoosePlayerStart_Implementation(AController* Player)
{
    if (IsValid(PreviewPlayerStart))
    {
        return PreviewPlayerStart;
    }

    return Super::ChoosePlayerStart_Implementation(Player);
}
