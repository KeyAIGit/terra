#include "TerraFirstPersonCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "InputCoreTypes.h"
#include "Net/UnrealNetwork.h"
#include "TerraInteractionComponent.h"

ATerraFirstPersonCharacter::ATerraFirstPersonCharacter()
{
    PrimaryActorTick.bCanEverTick = false;
    bReplicates = true;
    SetReplicateMovement(true);

    GetCapsuleComponent()->InitCapsuleSize(42.0F, 96.0F);

    bUseControllerRotationPitch = false;
    bUseControllerRotationYaw = true;
    bUseControllerRotationRoll = false;

    UCharacterMovementComponent* Movement = GetCharacterMovement();
    Movement->bOrientRotationToMovement = false;
    Movement->GetNavAgentPropertiesRef().bCanCrouch = true;
    Movement->BrakingDecelerationWalking = 1800.0F;
    Movement->AirControl = 0.25F;

    FirstPersonCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FirstPersonCamera"));
    FirstPersonCamera->SetupAttachment(GetCapsuleComponent());
    FirstPersonCamera->SetRelativeLocation(FVector(-10.0F, 0.0F, 64.0F));
    FirstPersonCamera->bUsePawnControlRotation = true;
    FirstPersonCamera->FieldOfView = 90.0F;

    InteractionComponent = CreateDefaultSubobject<UTerraInteractionComponent>(TEXT("InteractionComponent"));
}

void ATerraFirstPersonCharacter::BeginPlay()
{
    Super::BeginPlay();

    ApplyMovementSpeeds();
    InteractionComponent->SetTraceSource(FirstPersonCamera);
}

void ATerraFirstPersonCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
    check(PlayerInputComponent);
    Super::SetupPlayerInputComponent(PlayerInputComponent);

    // Bind physical keys directly so the foundation works before content-side Input Actions exist.
    PlayerInputComponent->BindAxisKey(EKeys::W, this, &ThisClass::MoveForward);
    PlayerInputComponent->BindAxisKey(EKeys::S, this, &ThisClass::MoveBackward);
    PlayerInputComponent->BindAxisKey(EKeys::D, this, &ThisClass::MoveRight);
    PlayerInputComponent->BindAxisKey(EKeys::A, this, &ThisClass::MoveLeft);
    PlayerInputComponent->BindAxisKey(EKeys::Gamepad_LeftY, this, &ThisClass::MoveForward);
    PlayerInputComponent->BindAxisKey(EKeys::Gamepad_LeftX, this, &ThisClass::MoveRight);

    PlayerInputComponent->BindAxisKey(EKeys::MouseX, this, &ThisClass::TurnMouse);
    PlayerInputComponent->BindAxisKey(EKeys::MouseY, this, &ThisClass::LookMouse);
    PlayerInputComponent->BindAxisKey(EKeys::Gamepad_RightX, this, &ThisClass::TurnGamepad);
    PlayerInputComponent->BindAxisKey(EKeys::Gamepad_RightY, this, &ThisClass::LookGamepad);

    PlayerInputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this, &ACharacter::Jump);
    PlayerInputComponent->BindKey(EKeys::SpaceBar, IE_Released, this, &ACharacter::StopJumping);
    PlayerInputComponent->BindKey(EKeys::Gamepad_FaceButton_Bottom, IE_Pressed, this, &ACharacter::Jump);
    PlayerInputComponent->BindKey(EKeys::Gamepad_FaceButton_Bottom, IE_Released, this, &ACharacter::StopJumping);

    PlayerInputComponent->BindKey(EKeys::LeftShift, IE_Pressed, this, &ThisClass::BeginSprint);
    PlayerInputComponent->BindKey(EKeys::LeftShift, IE_Released, this, &ThisClass::EndSprint);
    PlayerInputComponent->BindKey(EKeys::Gamepad_LeftThumbstick, IE_Pressed, this, &ThisClass::BeginSprint);
    PlayerInputComponent->BindKey(EKeys::Gamepad_LeftThumbstick, IE_Released, this, &ThisClass::EndSprint);

    PlayerInputComponent->BindKey(EKeys::C, IE_Pressed, this, &ThisClass::BeginCrouch);
    PlayerInputComponent->BindKey(EKeys::C, IE_Released, this, &ThisClass::EndCrouch);

    PlayerInputComponent->BindKey(EKeys::E, IE_Pressed, this, &ThisClass::TriggerInteraction);
    PlayerInputComponent->BindKey(EKeys::Gamepad_FaceButton_Left, IE_Pressed, this, &ThisClass::TriggerInteraction);
}

void ATerraFirstPersonCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(ThisClass, bIsSprinting);
}

void ATerraFirstPersonCharacter::SetSprinting(const bool bNewSprinting)
{
    if (bIsSprinting == bNewSprinting)
    {
        return;
    }

    bIsSprinting = bNewSprinting;
    ApplyMovementSpeeds();

    if (!HasAuthority())
    {
        ServerSetSprinting(bNewSprinting);
    }
}

void ATerraFirstPersonCharacter::ServerSetSprinting_Implementation(const bool bNewSprinting)
{
    SetSprinting(bNewSprinting);
}

void ATerraFirstPersonCharacter::OnRep_Sprinting()
{
    ApplyMovementSpeeds();
}

void ATerraFirstPersonCharacter::MoveForward(const float Value)
{
    if (Controller && !FMath::IsNearlyZero(Value))
    {
        const FRotator YawRotation(0.0F, Controller->GetControlRotation().Yaw, 0.0F);
        AddMovementInput(FRotationMatrix(YawRotation).GetUnitAxis(EAxis::X), Value);
    }
}

void ATerraFirstPersonCharacter::MoveBackward(const float Value)
{
    MoveForward(-Value);
}

void ATerraFirstPersonCharacter::MoveRight(const float Value)
{
    if (Controller && !FMath::IsNearlyZero(Value))
    {
        const FRotator YawRotation(0.0F, Controller->GetControlRotation().Yaw, 0.0F);
        AddMovementInput(FRotationMatrix(YawRotation).GetUnitAxis(EAxis::Y), Value);
    }
}

void ATerraFirstPersonCharacter::MoveLeft(const float Value)
{
    MoveRight(-Value);
}

void ATerraFirstPersonCharacter::TurnMouse(const float Value)
{
    AddControllerYawInput(Value * MouseLookSensitivity);
}

void ATerraFirstPersonCharacter::LookMouse(const float Value)
{
    AddControllerPitchInput(-Value * MouseLookSensitivity);
}

void ATerraFirstPersonCharacter::TurnGamepad(const float Value)
{
    const float DeltaSeconds = GetWorld() ? GetWorld()->GetDeltaSeconds() : 0.0F;
    AddControllerYawInput(Value * GamepadLookRate * DeltaSeconds);
}

void ATerraFirstPersonCharacter::LookGamepad(const float Value)
{
    const float DeltaSeconds = GetWorld() ? GetWorld()->GetDeltaSeconds() : 0.0F;
    AddControllerPitchInput(-Value * GamepadLookRate * DeltaSeconds);
}

void ATerraFirstPersonCharacter::BeginSprint()
{
    SetSprinting(true);
}

void ATerraFirstPersonCharacter::EndSprint()
{
    SetSprinting(false);
}

void ATerraFirstPersonCharacter::BeginCrouch()
{
    Crouch();
}

void ATerraFirstPersonCharacter::EndCrouch()
{
    UnCrouch();
}

void ATerraFirstPersonCharacter::TriggerInteraction()
{
    InteractionComponent->TryInteract();
}

void ATerraFirstPersonCharacter::ApplyMovementSpeeds()
{
    UCharacterMovementComponent* Movement = GetCharacterMovement();
    Movement->MaxWalkSpeed = bIsSprinting ? SprintSpeed : WalkSpeed;
    Movement->MaxWalkSpeedCrouched = CrouchedSpeed;
}
