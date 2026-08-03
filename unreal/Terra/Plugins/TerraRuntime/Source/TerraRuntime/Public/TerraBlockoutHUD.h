#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"

#include "TerraBlockoutHUD.generated.h"

/**
 * Asset-free disclosure overlay for engineering previews.
 *
 * The label is deliberately always visible in ATerraGameModeBase so a legacy
 * proxy scene cannot be mistaken for the promised reality simulation.
 */
UCLASS(NotBlueprintable)
class TERRARUNTIME_API ATerraBlockoutHUD : public AHUD
{
    GENERATED_BODY()

public:
    virtual void DrawHUD() override;
};
