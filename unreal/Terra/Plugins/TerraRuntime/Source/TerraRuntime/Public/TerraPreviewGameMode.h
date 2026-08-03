#pragma once

#include "CoreMinimal.h"
#include "TerraGameModeBase.h"

#include "TerraPreviewGameMode.generated.h"

class APlayerStart;
class ATerraPreviewEnvironment;

/**
 * Opt-in, asset-independent preview mode intended for /Engine/Maps/Entry.
 * It is a gameplay/camera test harness, not a simulation-content showcase.
 */
UCLASS(NotBlueprintable)
class TERRARUNTIME_API ATerraPreviewGameMode : public ATerraGameModeBase
{
    GENERATED_BODY()

public:
    ATerraPreviewGameMode();

    virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
    virtual void StartPlay() override;
    virtual AActor* ChoosePlayerStart_Implementation(AController* Player) override;

    static FTransform GetPreviewStartTransform();

private:
    UPROPERTY(Transient)
    TObjectPtr<ATerraPreviewEnvironment> PreviewEnvironment;

    UPROPERTY(Transient)
    TObjectPtr<APlayerStart> PreviewPlayerStart;
};
