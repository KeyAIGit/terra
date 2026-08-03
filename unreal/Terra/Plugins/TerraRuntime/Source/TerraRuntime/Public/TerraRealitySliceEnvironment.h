#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TerraRealitySliceLayout.h"

#include "TerraRealitySliceEnvironment.generated.h"

class UDirectionalLightComponent;
class UHierarchicalInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class USceneComponent;
class USkyAtmosphereComponent;
class USkyLightComponent;
class UStaticMesh;
class UTextRenderComponent;

/**
 * Asset-independent renderer/collision shell for one audited 150–250 m ward.
 * It is deliberately procedural massing: spatially usable, not photoreal art.
 */
UCLASS(NotBlueprintable)
class TERRARUNTIME_API ATerraRealitySliceEnvironment : public AActor
{
    GENERATED_BODY()

public:
    ATerraRealitySliceEnvironment();

    bool BuildFromLayout(const FTerraRealitySliceLayout& InLayout, FString& OutError);

    UFUNCTION(BlueprintPure, Category = "Terra|RealitySlice")
    int32 GetSourceElementCount() const { return SourceElementCount; }

    UFUNCTION(BlueprintPure, Category = "Terra|RealitySlice")
    int32 GetRenderedInstanceCount() const { return RenderedInstanceCount; }

    UFUNCTION(BlueprintPure, Category = "Terra|RealitySlice")
    int32 GetGateCollisionPierCount() const { return GateCollisionPierCount; }

    UFUNCTION(BlueprintPure, Category = "Terra|RealitySlice")
    float GetGateOpeningWidthCm() const { return GateOpeningWidthCm; }

private:
    UHierarchicalInstancedStaticMeshComponent* GetOrCreateBucket(
        ETerraRealitySliceElementKind Kind,
        bool bCollision,
        bool bCylinder,
        TMap<int32, UHierarchicalInstancedStaticMeshComponent*>& Buckets
    );

    bool AddGateInstances(
        const FTerraRealitySliceElement& Gate,
        TMap<int32, UHierarchicalInstancedStaticMeshComponent*>& Buckets,
        FString& OutError
    );

    void AddBoxLikeInstance(
        const FTerraRealitySliceElement& Element,
        bool bCylinder,
        TMap<int32, UHierarchicalInstancedStaticMeshComponent*>& Buckets
    );

    UPROPERTY(VisibleAnywhere, Category = "Terra|RealitySlice")
    TObjectPtr<USceneComponent> SceneRoot;

    UPROPERTY(VisibleAnywhere, Category = "Terra|RealitySlice")
    TObjectPtr<UTextRenderComponent> DisclosureText;

    UPROPERTY(VisibleAnywhere, Category = "Terra|RealitySlice")
    TObjectPtr<UDirectionalLightComponent> SunLight;

    UPROPERTY(VisibleAnywhere, Category = "Terra|RealitySlice")
    TObjectPtr<USkyLightComponent> SkyLight;

    UPROPERTY(VisibleAnywhere, Category = "Terra|RealitySlice")
    TObjectPtr<USkyAtmosphereComponent> SkyAtmosphere;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UHierarchicalInstancedStaticMeshComponent>> RuntimeMeshComponents;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UMaterialInstanceDynamic>> RuntimeMaterials;

    UPROPERTY(Transient)
    TObjectPtr<UStaticMesh> CubeMesh;

    UPROPERTY(Transient)
    TObjectPtr<UStaticMesh> CylinderMesh;

    UPROPERTY(Transient)
    TObjectPtr<UMaterialInterface> BasicMaterial;

    UPROPERTY(VisibleAnywhere, Category = "Terra|RealitySlice")
    int32 SourceElementCount = 0;

    UPROPERTY(VisibleAnywhere, Category = "Terra|RealitySlice")
    int32 RenderedInstanceCount = 0;

    UPROPERTY(VisibleAnywhere, Category = "Terra|RealitySlice")
    int32 GateCollisionPierCount = 0;

    UPROPERTY(VisibleAnywhere, Category = "Terra|RealitySlice", meta = (Units = "cm"))
    float GateOpeningWidthCm = 0.0F;
};
