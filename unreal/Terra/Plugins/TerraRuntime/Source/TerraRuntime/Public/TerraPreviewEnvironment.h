#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "TerraPreviewEnvironment.generated.h"

class UDirectionalLightComponent;
class USceneComponent;
class USkyAtmosphereComponent;
class USkyLightComponent;
class UStaticMeshComponent;
class UTextRenderComponent;

/**
 * Small asset-independent test pad for validating camera, locomotion and floor
 * collision without presenting generated proxy-city content as a finished world.
 */
UCLASS(NotBlueprintable)
class TERRARUNTIME_API ATerraPreviewEnvironment : public AActor
{
    GENERATED_BODY()

public:
    ATerraPreviewEnvironment();

    UFUNCTION(BlueprintPure, Category = "Terra|Preview")
    UStaticMeshComponent* GetGround() const { return Ground; }

private:
    UPROPERTY(VisibleAnywhere, Category = "Terra|Preview")
    TObjectPtr<USceneComponent> SceneRoot;

    UPROPERTY(VisibleAnywhere, Category = "Terra|Preview")
    TObjectPtr<UStaticMeshComponent> Ground;

    UPROPERTY(VisibleAnywhere, Category = "Terra|Preview")
    TObjectPtr<UStaticMeshComponent> NearMarker;

    UPROPERTY(VisibleAnywhere, Category = "Terra|Preview")
    TObjectPtr<UStaticMeshComponent> FarMarker;

    UPROPERTY(VisibleAnywhere, Category = "Terra|Preview")
    TObjectPtr<UTextRenderComponent> DisclosureText;

    UPROPERTY(VisibleAnywhere, Category = "Terra|Preview")
    TObjectPtr<UDirectionalLightComponent> SunLight;

    UPROPERTY(VisibleAnywhere, Category = "Terra|Preview")
    TObjectPtr<USkyLightComponent> SkyLight;

    UPROPERTY(VisibleAnywhere, Category = "Terra|Preview")
    TObjectPtr<USkyAtmosphereComponent> SkyAtmosphere;
};
