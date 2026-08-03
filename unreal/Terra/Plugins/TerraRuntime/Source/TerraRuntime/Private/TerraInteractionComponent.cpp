#include "TerraInteractionComponent.h"

#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "TerraInteractable.h"
#include "TerraRuntimeModule.h"

UTerraInteractionComponent::UTerraInteractionComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.bStartWithTickEnabled = true;
    PrimaryComponentTick.TickInterval = 0.05F;
    SetIsReplicatedByDefault(true);
}

void UTerraInteractionComponent::BeginPlay()
{
    Super::BeginPlay();

    if (const APawn* OwnerPawn = Cast<APawn>(GetOwner()); OwnerPawn && OwnerPawn->IsLocallyControlled())
    {
        RefreshFocus();
    }
}

void UTerraInteractionComponent::TickComponent(
    const float DeltaTime,
    const ELevelTick TickType,
    FActorComponentTickFunction* ThisTickFunction
)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

    const APawn* OwnerPawn = Cast<APawn>(GetOwner());
    if (OwnerPawn && OwnerPawn->IsLocallyControlled())
    {
        RefreshFocus();
    }
}

void UTerraInteractionComponent::SetTraceSource(USceneComponent* InTraceSource)
{
    TraceSource = InTraceSource;
    RefreshFocus();
}

void UTerraInteractionComponent::RefreshFocus()
{
    SetFocusedActor(FindCandidate());
}

bool UTerraInteractionComponent::TryInteract()
{
    if (!CanUseCandidate(FocusedActor))
    {
        RefreshFocus();
    }

    if (!CanUseCandidate(FocusedActor))
    {
        return false;
    }

    if (GetOwner() && GetOwner()->HasAuthority())
    {
        return PerformInteraction(FocusedActor);
    }

    ServerTryInteract(FocusedActor);
    return true;
}

void UTerraInteractionComponent::ServerTryInteract_Implementation(AActor* Candidate)
{
    // The client may suggest a target, but the server independently traces and validates it.
    if (Candidate && Candidate == FindCandidate())
    {
        PerformInteraction(Candidate);
    }
    else
    {
        UE_LOG(
            LogTerraRuntime,
            Verbose,
            TEXT("Rejected interaction from %s: server could not validate target %s."),
            *GetNameSafe(GetOwner()),
            *GetNameSafe(Candidate)
        );
    }
}

AActor* UTerraInteractionComponent::FindCandidate() const
{
    const UWorld* World = GetWorld();
    const AActor* OwnerActor = GetOwner();
    if (!World || !OwnerActor || InteractionDistance <= 0.0F)
    {
        return nullptr;
    }

    FVector TraceStart;
    FRotator TraceRotation;
    GetTraceView(TraceStart, TraceRotation);
    const FVector TraceEnd = TraceStart + TraceRotation.Vector() * InteractionDistance;

    FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(TerraInteractionTrace), bTraceComplex, OwnerActor);
    FHitResult Hit;
    bool bHit = false;

    if (TraceRadius > UE_KINDA_SMALL_NUMBER)
    {
        bHit = World->SweepSingleByChannel(
            Hit,
            TraceStart,
            TraceEnd,
            FQuat::Identity,
            TraceChannel,
            FCollisionShape::MakeSphere(TraceRadius),
            QueryParams
        );
    }
    else
    {
        bHit = World->LineTraceSingleByChannel(
            Hit,
            TraceStart,
            TraceEnd,
            TraceChannel,
            QueryParams
        );
    }

    AActor* Candidate = bHit ? Hit.GetActor() : nullptr;
    return CanUseCandidate(Candidate) ? Candidate : nullptr;
}

bool UTerraInteractionComponent::CanUseCandidate(AActor* Candidate) const
{
    const APawn* OwnerPawn = Cast<APawn>(GetOwner());
    return IsValid(Candidate)
        && IsValid(OwnerPawn)
        && Candidate != OwnerPawn
        && Candidate->GetClass()->ImplementsInterface(UTerraInteractable::StaticClass())
        && ITerraInteractable::Execute_CanInteract(Candidate, const_cast<APawn*>(OwnerPawn));
}

bool UTerraInteractionComponent::PerformInteraction(AActor* Candidate)
{
    APawn* OwnerPawn = Cast<APawn>(GetOwner());
    if (!CanUseCandidate(Candidate) || !OwnerPawn)
    {
        return false;
    }

    ITerraInteractable::Execute_Interact(Candidate, OwnerPawn);
    return true;
}

void UTerraInteractionComponent::SetFocusedActor(AActor* NewActor)
{
    FText NewPrompt;
    if (CanUseCandidate(NewActor))
    {
        NewPrompt = ITerraInteractable::Execute_GetInteractionPrompt(NewActor, Cast<APawn>(GetOwner()));
    }
    else
    {
        NewActor = nullptr;
    }

    if (FocusedActor == NewActor && ActivePrompt.EqualTo(NewPrompt))
    {
        return;
    }

    AActor* PreviousActor = FocusedActor;
    FocusedActor = NewActor;
    ActivePrompt = MoveTemp(NewPrompt);
    OnInteractionTargetChanged.Broadcast(PreviousActor, FocusedActor, ActivePrompt);
}

void UTerraInteractionComponent::GetTraceView(FVector& OutLocation, FRotator& OutRotation) const
{
    if (IsValid(TraceSource))
    {
        OutLocation = TraceSource->GetComponentLocation();
        OutRotation = TraceSource->GetComponentRotation();
        return;
    }

    if (const APawn* OwnerPawn = Cast<APawn>(GetOwner()))
    {
        OwnerPawn->GetActorEyesViewPoint(OutLocation, OutRotation);
        return;
    }

    const AActor* OwnerActor = GetOwner();
    OutLocation = OwnerActor ? OwnerActor->GetActorLocation() : FVector::ZeroVector;
    OutRotation = OwnerActor ? OwnerActor->GetActorRotation() : FRotator::ZeroRotator;
}
