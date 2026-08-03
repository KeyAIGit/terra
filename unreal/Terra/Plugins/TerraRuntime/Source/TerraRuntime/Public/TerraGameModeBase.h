#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"

#include "TerraGameModeBase.generated.h"

/** Minimal game mode that makes Terra's first-person pawn immediately selectable in a map. */
UCLASS(Blueprintable)
class TERRARUNTIME_API ATerraGameModeBase : public AGameModeBase
{
    GENERATED_BODY()

public:
    ATerraGameModeBase();
};
