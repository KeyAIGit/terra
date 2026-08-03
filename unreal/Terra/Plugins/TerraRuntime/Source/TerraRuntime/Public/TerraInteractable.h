#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"

#include "TerraInteractable.generated.h"

class APawn;

UINTERFACE(BlueprintType)
class TERRARUNTIME_API UTerraInteractable : public UInterface
{
    GENERATED_BODY()
};

/** Implement on any actor that the player can focus and use. */
class TERRARUNTIME_API ITerraInteractable
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Terra|Interaction")
    bool CanInteract(APawn* Interactor) const;
    virtual bool CanInteract_Implementation(APawn* Interactor) const { return Interactor != nullptr; }

    UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Terra|Interaction")
    FText GetInteractionPrompt(APawn* Interactor) const;
    virtual FText GetInteractionPrompt_Implementation(APawn* Interactor) const
    {
        return NSLOCTEXT("TerraInteractable", "DefaultInteractionPrompt", "Interact");
    }

    UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Terra|Interaction")
    void Interact(APawn* Interactor);
    virtual void Interact_Implementation(APawn* Interactor) { }
};
