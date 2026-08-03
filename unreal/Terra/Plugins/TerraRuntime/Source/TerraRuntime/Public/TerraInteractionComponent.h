#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/EngineTypes.h"

#include "TerraInteractionComponent.generated.h"

class AActor;
class APawn;
class USceneComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(
    FTerraInteractionTargetChanged,
    AActor*, PreviousActor,
    AActor*, NewActor,
    FText, Prompt
);

/** Finds an interactable in the player's view and performs an authority-validated interaction. */
UCLASS(ClassGroup = (Terra), BlueprintType, meta = (BlueprintSpawnableComponent))
class TERRARUNTIME_API UTerraInteractionComponent final : public UActorComponent
{
    GENERATED_BODY()

public:
    UTerraInteractionComponent();

    virtual void TickComponent(
        float DeltaTime,
        ELevelTick TickType,
        FActorComponentTickFunction* ThisTickFunction
    ) override;

    UFUNCTION(BlueprintCallable, Category = "Terra|Interaction")
    void SetTraceSource(USceneComponent* InTraceSource);

    UFUNCTION(BlueprintCallable, Category = "Terra|Interaction")
    void RefreshFocus();

    /** Returns true when a valid interaction was performed or submitted to the server. */
    UFUNCTION(BlueprintCallable, Category = "Terra|Interaction")
    bool TryInteract();

    UFUNCTION(BlueprintPure, Category = "Terra|Interaction")
    AActor* GetFocusedActor() const { return FocusedActor; }

    UFUNCTION(BlueprintPure, Category = "Terra|Interaction")
    FText GetActivePrompt() const { return ActivePrompt; }

    UPROPERTY(BlueprintAssignable, Category = "Terra|Interaction")
    FTerraInteractionTargetChanged OnInteractionTargetChanged;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Interaction", meta = (ClampMin = "1.0", Units = "cm"))
    float InteractionDistance = 350.0F;

    /** A small radius is more forgiving than a line trace. Set to zero for an exact ray. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Interaction", meta = (ClampMin = "0.0", Units = "cm"))
    float TraceRadius = 8.0F;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Interaction")
    TEnumAsByte<ECollisionChannel> TraceChannel = ECC_Visibility;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Interaction")
    bool bTraceComplex = false;

protected:
    virtual void BeginPlay() override;

    UFUNCTION(Server, Reliable)
    void ServerTryInteract(AActor* Candidate);

private:
    AActor* FindCandidate() const;
    bool CanUseCandidate(AActor* Candidate) const;
    bool PerformInteraction(AActor* Candidate);
    void SetFocusedActor(AActor* NewActor);
    void GetTraceView(FVector& OutLocation, FRotator& OutRotation) const;

    UPROPERTY(Transient)
    TObjectPtr<USceneComponent> TraceSource;

    UPROPERTY(Transient)
    TObjectPtr<AActor> FocusedActor;

    UPROPERTY(Transient)
    FText ActivePrompt;
};
