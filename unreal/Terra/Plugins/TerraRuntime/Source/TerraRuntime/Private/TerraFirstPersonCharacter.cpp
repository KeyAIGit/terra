#include "TerraFirstPersonCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Engine/HitResult.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "InputCoreTypes.h"
#include "Net/UnrealNetwork.h"
#include "TerraInteractionComponent.h"
#include "TerraRuntimeModule.h"
#include "TimerManager.h"

namespace TerraFirstPerson
{
constexpr float SpawnProbeHeight = 5000.0F;
constexpr float SpawnProbeDepth = 10000.0F;
constexpr float SuspiciousFloorDelta = 50.0F;

struct FFloorProbe
{
    bool bHit = false;
    FHitResult Hit;
};

FFloorProbe ProbeFloor(const ATerraFirstPersonCharacter& Character, const bool bTraceComplex)
{
    FFloorProbe Result;
    const UWorld* World = Character.GetWorld();
    if (!World)
    {
        return Result;
    }

    const FVector PawnLocation = Character.GetActorLocation();
    const FVector Start = PawnLocation + FVector::UpVector * SpawnProbeHeight;
    const FVector End = PawnLocation - FVector::UpVector * SpawnProbeDepth;
    FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(TerraSpawnFloorProbe), false, &Character);
    QueryParams.bTraceComplex = bTraceComplex;
    Result.bHit = World->LineTraceSingleByChannel(Result.Hit, Start, End, ECC_Visibility, QueryParams);
    return Result;
}

FString DescribeFloor(const FFloorProbe& Probe)
{
    if (!Probe.bHit)
    {
        return TEXT("none");
    }

    return FString::Printf(
        TEXT("z=%.2f actor=%s component=%s"),
        Probe.Hit.ImpactPoint.Z,
        *GetNameSafe(Probe.Hit.GetActor()),
        *GetNameSafe(Probe.Hit.GetComponent())
    );
}
} // namespace TerraFirstPerson

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

    // BeginPlay commonly runs before possession. PossessedBy/OnRep_Controller are
    // the primary paths; the next-tick fallback covers pre-possessed pawns.
    if (UWorld* World = GetWorld())
    {
        World->GetTimerManager().SetTimerForNextTick(
            FTimerDelegate::CreateWeakLambda(this, [this]() { InitializeLocalView(TEXT("BeginPlayNextTick")); })
        );
    }
}

void ATerraFirstPersonCharacter::PossessedBy(AController* NewController)
{
    Super::PossessedBy(NewController);
    InitializeLocalView(TEXT("PossessedBy"));
}

void ATerraFirstPersonCharacter::OnRep_Controller()
{
    Super::OnRep_Controller();
    InitializeLocalView(TEXT("OnRep_Controller"));
}

float ATerraFirstPersonCharacter::SanitizeLookInput(const float Value, const float MaxAbsoluteValue)
{
    if (!FMath::IsFinite(Value) || !FMath::IsFinite(MaxAbsoluteValue) || MaxAbsoluteValue <= 0.0F)
    {
        return 0.0F;
    }

    return FMath::Clamp(Value, -MaxAbsoluteValue, MaxAbsoluteValue);
}

void ATerraFirstPersonCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
    check(PlayerInputComponent);
    Super::SetupPlayerInputComponent(PlayerInputComponent);

    // Named mappings support both digital keys and true analog axes without
    // passing button keys to BindAxisKey (which requires a 1D axis key).
    PlayerInputComponent->BindAxis(TEXT("TerraMoveForward"), this, &ThisClass::MoveForward);
    PlayerInputComponent->BindAxis(TEXT("TerraMoveRight"), this, &ThisClass::MoveRight);
    PlayerInputComponent->BindAxis(TEXT("TerraTurnMouse"), this, &ThisClass::TurnMouse);
    PlayerInputComponent->BindAxis(TEXT("TerraLookMouse"), this, &ThisClass::LookMouse);
    PlayerInputComponent->BindAxis(TEXT("TerraTurnGamepad"), this, &ThisClass::TurnGamepad);
    PlayerInputComponent->BindAxis(TEXT("TerraLookGamepad"), this, &ThisClass::LookGamepad);

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

void ATerraFirstPersonCharacter::MoveRight(const float Value)
{
    if (Controller && !FMath::IsNearlyZero(Value))
    {
        const FRotator YawRotation(0.0F, Controller->GetControlRotation().Yaw, 0.0F);
        AddMovementInput(FRotationMatrix(YawRotation).GetUnitAxis(EAxis::Y), Value);
    }
}

void ATerraFirstPersonCharacter::TurnMouse(const float Value)
{
    InitializeLocalView(TEXT("TurnMouse"));
    const UWorld* World = GetWorld();
    if (!bInitialViewInitialized || !World || World->GetTimeSeconds() < MouseLookEnableTime)
    {
        return;
    }

    const float SafeValue = SanitizeLookInput(Value, MaxMouseLookInputPerFrame);
    AddControllerYawInput(SafeValue * MouseLookSensitivity);
}

void ATerraFirstPersonCharacter::LookMouse(const float Value)
{
    InitializeLocalView(TEXT("LookMouse"));
    const UWorld* World = GetWorld();
    if (!bInitialViewInitialized || !World || World->GetTimeSeconds() < MouseLookEnableTime)
    {
        return;
    }

    const float SafeValue = SanitizeLookInput(Value, MaxMouseLookInputPerFrame);
    AddControllerPitchInput(-SafeValue * MouseLookSensitivity);
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

void ATerraFirstPersonCharacter::InitializeLocalView(const TCHAR* Context)
{
    if (bInitialViewInitialized || !Controller)
    {
        return;
    }

    // IsLocallyControlled is authoritative for network play. The standalone
    // fallback also makes headless functional worlds deterministic.
    if (!IsLocallyControlled() && GetNetMode() != NM_Standalone)
    {
        return;
    }

    const FRotator InitialView(0.0F, GetActorRotation().Yaw, 0.0F);
    Controller->SetControlRotation(InitialView);
    bInitialViewInitialized = true;

    if (const UWorld* World = GetWorld())
    {
        MouseLookEnableTime = World->GetTimeSeconds() + FMath::Max(0.0F, InitialMouseLookDelay);
    }

    UE_LOG(
        LogTerraRuntime,
        Display,
        TEXT("Initial view stabilized: context=%s pawn=%s actor_rotation=%s control_rotation=%s mouse_delay=%.2fs"),
        Context,
        *GetName(),
        *GetActorRotation().ToCompactString(),
        *Controller->GetControlRotation().ToCompactString(),
        InitialMouseLookDelay
    );

    if (!bSpawnDiagnosticsScheduled)
    {
        bSpawnDiagnosticsScheduled = true;
        if (UWorld* World = GetWorld())
        {
            World->GetTimerManager().SetTimerForNextTick(
                FTimerDelegate::CreateWeakLambda(this, [this]() { ReportSpawnDiagnostics(); })
            );
        }
    }
}

void ATerraFirstPersonCharacter::ReportSpawnDiagnostics()
{
    const UCapsuleComponent* Capsule = GetCapsuleComponent();
    const FVector PawnLocation = GetActorLocation();
    const FVector CameraLocation = FirstPersonCamera ? FirstPersonCamera->GetComponentLocation() : PawnLocation;
    const FRotator ControlRotation = Controller ? Controller->GetControlRotation() : FRotator::ZeroRotator;
    const float CapsuleHalfHeight = Capsule ? Capsule->GetScaledCapsuleHalfHeight() : 0.0F;
    const float CapsuleBottomZ = PawnLocation.Z - CapsuleHalfHeight;

    const TerraFirstPerson::FFloorProbe SimpleFloor = TerraFirstPerson::ProbeFloor(*this, false);
    const TerraFirstPerson::FFloorProbe ComplexFloor = TerraFirstPerson::ProbeFloor(*this, true);
    const bool bComparableFloors = SimpleFloor.bHit && ComplexFloor.bHit;
    const float FloorDelta = bComparableFloors
        ? FMath::Abs(SimpleFloor.Hit.ImpactPoint.Z - ComplexFloor.Hit.ImpactPoint.Z)
        : 0.0F;

    UE_LOG(
        LogTerraRuntime,
        Display,
        TEXT("Spawn diagnostics: pawn=%s location=%s rotation=%s control=%s camera=%s capsule_bottom_z=%.2f simple_floor=[%s] complex_floor=[%s] floor_delta=%.2f"),
        *GetName(),
        *PawnLocation.ToCompactString(),
        *GetActorRotation().ToCompactString(),
        *ControlRotation.ToCompactString(),
        *CameraLocation.ToCompactString(),
        CapsuleBottomZ,
        *TerraFirstPerson::DescribeFloor(SimpleFloor),
        *TerraFirstPerson::DescribeFloor(ComplexFloor),
        FloorDelta
    );

    if (bComparableFloors && FloorDelta > TerraFirstPerson::SuspiciousFloorDelta)
    {
        UE_LOG(
            LogTerraRuntime,
            Warning,
            TEXT("Spawn floor mismatch is %.2f cm. The imported surface likely uses coarse simple convex collision; use complex-as-simple or a dedicated walkable collision mesh before treating this map as playable."),
            FloorDelta
        );
    }
}
