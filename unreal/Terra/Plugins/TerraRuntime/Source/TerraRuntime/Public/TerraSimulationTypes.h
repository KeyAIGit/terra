#pragma once

#include "CoreMinimal.h"
#include "UObject/SoftObjectPtr.h"

#include "TerraSimulationTypes.generated.h"

class UWorld;

/** How strongly a piece of Terra data is grounded in evidence. */
UENUM(BlueprintType)
enum class ETerraDataAuthority : uint8
{
    Unknown UMETA(DisplayName = "Unknown"),
    Known UMETA(DisplayName = "Known / directly sourced"),
    Typical UMETA(DisplayName = "Typical / evidence-based"),
    Reconstructed UMETA(DisplayName = "Reconstructed"),
    Simulated UMETA(DisplayName = "Simulation output")
};

/** Geographic position in WGS84-style degrees and meters above mean sea level. */
USTRUCT(BlueprintType)
struct TERRARUNTIME_API FTerraGeoCoordinate
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Geography", meta = (ClampMin = "-90.0", ClampMax = "90.0"))
    double Latitude = 0.0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Geography", meta = (ClampMin = "-180.0", ClampMax = "180.0"))
    double Longitude = 0.0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Geography")
    double ElevationMeters = 0.0;
};

/** A normalized physiological or social need. Zero is depleted; one is satisfied. */
USTRUCT(BlueprintType)
struct TERRARUNTIME_API FTerraNeedState
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    FName NeedId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC", meta = (ClampMin = "0.0", ClampMax = "1.0"))
    float Satisfaction = 1.0F;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC", meta = (ClampMin = "0.0"))
    float ChangePerSimulatedHour = 0.0F;
};

/** Compact memory record suitable for deterministic save/load and later semantic expansion. */
USTRUCT(BlueprintType)
struct TERRARUNTIME_API FTerraMemoryRecord
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    FGuid MemoryId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    FName EventType = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    FString Summary;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    int64 SimulationTick = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC", meta = (ClampMin = "0.0", ClampMax = "1.0"))
    float EmotionalWeight = 0.0F;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    ETerraDataAuthority Authority = ETerraDataAuthority::Simulated;
};

/** Stable identity and authored traits for one simulated person. */
USTRUCT(BlueprintType)
struct TERRARUNTIME_API FTerraNPCDefinition
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    int32 SchemaVersion = 1;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    FGuid PersonId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    FText DisplayName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    FString CultureId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    FString PrimaryLanguageId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    FString OccupationId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    int32 BirthYear = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    TArray<FName> TraitIds;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    TMap<FName, FString> Metadata;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|NPC")
    ETerraDataAuthority Authority = ETerraDataAuthority::Simulated;
};

/** Mutable, save-game-friendly state separated from a person's stable definition. */
USTRUCT(BlueprintType)
struct TERRARUNTIME_API FTerraNPCRuntimeState
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Terra|NPC")
    FGuid PersonId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Terra|NPC")
    int64 LastSimulationTick = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Terra|NPC")
    bool bIsAlive = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Terra|NPC")
    FTransform WorldTransform = FTransform::Identity;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Terra|NPC")
    FName CurrentActivityId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Terra|NPC")
    TArray<FTerraNeedState> Needs;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Terra|NPC")
    TArray<FTerraMemoryRecord> Memories;
};

/** Complete hand-off unit from simulation/export code to one streamed Unreal scene. */
USTRUCT(BlueprintType)
struct TERRARUNTIME_API FTerraSceneDefinition
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    int32 SchemaVersion = 1;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    FGuid SceneId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    FString SimulationRunId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    int64 SimulationTick = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    int32 CalendarYear = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    FString EraId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    FString RegionId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    FTerraGeoCoordinate GeographicOrigin;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    TSoftObjectPtr<UWorld> WorldAsset;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    TArray<FTerraNPCDefinition> Population;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    TArray<FTerraNPCRuntimeState> InitialPopulationState;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    TMap<FName, FString> Metadata;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Scene")
    ETerraDataAuthority Authority = ETerraDataAuthority::Simulated;
};
