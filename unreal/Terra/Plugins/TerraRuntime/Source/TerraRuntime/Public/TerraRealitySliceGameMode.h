#pragma once

#include "CoreMinimal.h"
#include "TerraGameModeBase.h"
#include "TerraRealitySliceLayout.h"

#include "TerraRealitySliceGameMode.generated.h"

class APlayerStart;
class ATerraRealitySliceEnvironment;

/** Opt-in procedural ward mode intended for /Engine/Maps/Entry. */
UCLASS(NotBlueprintable)
class TERRARUNTIME_API ATerraRealitySliceGameMode : public ATerraGameModeBase
{
    GENERATED_BODY()

public:
    ATerraRealitySliceGameMode();

    virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
    virtual void StartPlay() override;
    virtual AActor* ChoosePlayerStart_Implementation(AController* Player) override;

    UFUNCTION(BlueprintPure, Category = "Terra|RealitySlice")
    const FTerraRealitySliceLayout& GetLoadedLayout() const { return LoadedLayout; }

private:
    UPROPERTY(Transient)
    TObjectPtr<ATerraRealitySliceEnvironment> RealitySliceEnvironment;

    UPROPERTY(Transient)
    TObjectPtr<APlayerStart> RealitySlicePlayerStart;

    UPROPERTY(Transient)
    FTerraRealitySliceLayout LoadedLayout;

    FString LoadDiagnostic;
};
