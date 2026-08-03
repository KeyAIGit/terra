#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"

#include "TerraFirstPersonCharacter.generated.h"

class UCameraComponent;
class UInputComponent;
class UTerraInteractionComponent;
class FLifetimeProperty;

/** Asset-independent first-person pawn for the initial playable vertical slice. */
UCLASS(Blueprintable)
class TERRARUNTIME_API ATerraFirstPersonCharacter : public ACharacter
{
    GENERATED_BODY()

public:
    ATerraFirstPersonCharacter();

    virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    virtual void PossessedBy(AController* NewController) override;
    virtual void OnRep_Controller() override;

    /** Clamp an input sample before it can turn a window-capture spike into a camera jump. */
    static float SanitizeLookInput(float Value, float MaxAbsoluteValue);

    UFUNCTION(BlueprintPure, Category = "Terra|Character")
    UCameraComponent* GetFirstPersonCamera() const { return FirstPersonCamera; }

    UFUNCTION(BlueprintPure, Category = "Terra|Character")
    UTerraInteractionComponent* GetInteractionComponent() const { return InteractionComponent; }

    UFUNCTION(BlueprintCallable, Category = "Terra|Character")
    void SetSprinting(bool bNewSprinting);

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Character|Movement", meta = (ClampMin = "0.0", Units = "cm/s"))
    float WalkSpeed = 400.0F;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Character|Movement", meta = (ClampMin = "0.0", Units = "cm/s"))
    float SprintSpeed = 650.0F;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Character|Movement", meta = (ClampMin = "0.0", Units = "cm/s"))
    float CrouchedSpeed = 220.0F;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Character|View", meta = (ClampMin = "0.0"))
    float MouseLookSensitivity = 1.0F;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Character|View", meta = (ClampMin = "0.0", Units = "deg/s"))
    float GamepadLookRate = 120.0F;

    /** Mouse input is ignored briefly while a standalone window captures and recenters the pointer. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Character|View", meta = (ClampMin = "0.0", ClampMax = "2.0", Units = "s"))
    float InitialMouseLookDelay = 0.35F;

    /** Maximum accepted mouse-axis sample in one frame. Normal motion is far below this value. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Terra|Character|View", meta = (ClampMin = "0.1", ClampMax = "90.0", Units = "deg"))
    float MaxMouseLookInputPerFrame = 8.0F;

    UPROPERTY(BlueprintReadOnly, ReplicatedUsing = OnRep_Sprinting, Category = "Terra|Character|Movement")
    bool bIsSprinting = false;

protected:
    virtual void BeginPlay() override;

private:
    void InitializeLocalView(const TCHAR* Context);
    void ReportSpawnDiagnostics();
    void MoveForward(float Value);
    void MoveRight(float Value);
    void TurnMouse(float Value);
    void LookMouse(float Value);
    void TurnGamepad(float Value);
    void LookGamepad(float Value);
    void BeginSprint();
    void EndSprint();
    void BeginCrouch();
    void EndCrouch();
    void TriggerInteraction();
    void ApplyMovementSpeeds();

    UFUNCTION(Server, Reliable)
    void ServerSetSprinting(bool bNewSprinting);

    UFUNCTION()
    void OnRep_Sprinting();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Terra|Character", meta = (AllowPrivateAccess = "true"))
    TObjectPtr<UCameraComponent> FirstPersonCamera;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Terra|Character", meta = (AllowPrivateAccess = "true"))
    TObjectPtr<UTerraInteractionComponent> InteractionComponent;

    double MouseLookEnableTime = 0.0;
    bool bInitialViewInitialized = false;
    bool bSpawnDiagnosticsScheduled = false;
};
