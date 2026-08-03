#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "TerraSimulationTypes.h"

#include "TerraDataAssets.generated.h"

/** Designer-facing asset for a reusable person definition and initial state. */
UCLASS(BlueprintType)
class TERRARUNTIME_API UTerraNPCDataAsset final : public UPrimaryDataAsset
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Terra|NPC")
    FTerraNPCDefinition Definition;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Terra|NPC")
    FTerraNPCRuntimeState InitialState;
};

/** Designer-facing asset representing one exported or authored playable scene. */
UCLASS(BlueprintType)
class TERRARUNTIME_API UTerraSceneDataAsset final : public UPrimaryDataAsset
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Terra|Scene")
    FTerraSceneDefinition Scene;
};
