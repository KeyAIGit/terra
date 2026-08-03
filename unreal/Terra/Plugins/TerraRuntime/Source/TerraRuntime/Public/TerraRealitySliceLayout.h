#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "TerraRealitySliceLayout.generated.h"

/** Runtime rendering/collision category for one spatial-prototype element. */
UENUM(BlueprintType)
enum class ETerraRealitySliceElementKind : uint8
{
    Ground,
    Road,
    Building,
    Roof,
    Door,
    Window,
    Awning,
    MarketStall,
    Well,
    Wall,
    Gate,
    Courtyard,
    PublicSpace
};

USTRUCT(BlueprintType)
struct TERRARUNTIME_API FTerraRealitySliceElement
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice")
    FString ElementId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice")
    ETerraRealitySliceElementKind Kind = ETerraRealitySliceElementKind::Building;

    /** Transform center in centimetres, after the source anchor is removed from XY. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice", meta = (Units = "cm"))
    FVector LocationCm = FVector::ZeroVector;

    /** Full X/Y/Z extents in centimetres. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice", meta = (Units = "cm"))
    FVector SizeCm = FVector(100.0, 100.0, 100.0);

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice", meta = (Units = "deg"))
    float YawDeg = 0.0F;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice", meta = (Units = "deg"))
    float PitchDeg = 0.0F;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice")
    bool bCollision = true;
};

USTRUCT(BlueprintType)
struct TERRARUNTIME_API FTerraRealitySlicePlayerStart
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice", meta = (Units = "cm"))
    FVector LocationCm = FVector(0.0, 0.0, 120.0);

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice", meta = (Units = "deg"))
    float YawDeg = 90.0F;
};

/** Normalized runtime layout. It represents one ward, never the complete city. */
USTRUCT(BlueprintType)
struct TERRARUNTIME_API FTerraRealitySliceLayout
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice")
    int32 SchemaVersion = 1;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice")
    FString LayoutId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice")
    FString Title;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice", meta = (Units = "cm"))
    FVector2D ExtentCm = FVector2D(20000.0, 20000.0);

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice")
    FTerraRealitySlicePlayerStart PlayerStart;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|RealitySlice")
    TArray<FTerraRealitySliceElement> Elements;

    /** Source-space audit anchor. X/Y are removed and Z is flattened to an explicit engineering datum. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Terra|RealitySlice", meta = (Units = "cm"))
    FVector SourceAnchorCm = FVector::ZeroVector;

    /** True when an unsafe source spawn was moved to the nearest deterministic pedestrian point. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Terra|RealitySlice")
    bool bPlayerStartRelocated = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Terra|RealitySlice")
    FString PlayerStartDiagnostic;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Terra|RealitySlice")
    FString SourcePath;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Terra|RealitySlice")
    bool bUsedFallback = false;
};

/** Strict runtime-adapter loader plus permissive rich-layout conversion and safe fallback. */
UCLASS()
class TERRARUNTIME_API UTerraRealitySliceLayoutLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "Terra|RealitySlice")
    static bool LoadBestAvailableLayout(FTerraRealitySliceLayout& OutLayout, FString& OutDiagnostic);

    UFUNCTION(BlueprintCallable, Category = "Terra|RealitySlice")
    static bool LoadLayoutFromJsonFile(
        const FString& JsonPath,
        FTerraRealitySliceLayout& OutLayout,
        FString& OutError
    );

    UFUNCTION(BlueprintCallable, Category = "Terra|RealitySlice")
    static bool ValidateLayout(const FTerraRealitySliceLayout& Layout, FString& OutError);

    UFUNCTION(BlueprintPure, Category = "Terra|RealitySlice")
    static FString GetGeneratedRuntimeLayoutPath();

    /** Capsule/road-footprint check used both by validation and runtime spawning. */
    static bool IsPlayerStartClear(
        const FTerraRealitySliceLayout& Layout,
        const FVector& CandidateLocationCm,
        FString& OutReason
    );

    /** Keeps a clear source spawn or deterministically relocates it onto pedestrian ground. */
    static bool ResolveSafePlayerStart(FTerraRealitySliceLayout& Layout, FString& OutDiagnostic);

    static FTerraRealitySliceLayout MakeSafeFallbackLayout();
};
