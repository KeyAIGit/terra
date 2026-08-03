#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"

#include "TerraRealitySliceHUD.generated.h"

/** Persistent truth-in-advertising overlay for the procedural ward. */
UCLASS(NotBlueprintable)
class TERRARUNTIME_API ATerraRealitySliceHUD : public AHUD
{
    GENERATED_BODY()

public:
    virtual void DrawHUD() override;
};
