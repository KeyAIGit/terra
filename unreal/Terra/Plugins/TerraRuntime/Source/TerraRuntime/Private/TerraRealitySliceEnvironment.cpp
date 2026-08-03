#include "TerraRealitySliceEnvironment.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

namespace TerraRealitySliceEnvironment
{
constexpr double GateMinimumOpeningWidthCm = 600.0;
constexpr double GateMinimumPierWidthCm = 120.0;

FLinearColor ColorForKind(const ETerraRealitySliceElementKind Kind)
{
    switch (Kind)
    {
    case ETerraRealitySliceElementKind::Ground: return FLinearColor(0.18F, 0.145F, 0.095F);
    case ETerraRealitySliceElementKind::Road: return FLinearColor(0.32F, 0.255F, 0.16F);
    case ETerraRealitySliceElementKind::Building: return FLinearColor(0.56F, 0.38F, 0.22F);
    case ETerraRealitySliceElementKind::Roof: return FLinearColor(0.24F, 0.095F, 0.055F);
    case ETerraRealitySliceElementKind::Door: return FLinearColor(0.12F, 0.055F, 0.025F);
    case ETerraRealitySliceElementKind::Window: return FLinearColor(0.16F, 0.38F, 0.48F);
    case ETerraRealitySliceElementKind::Awning: return FLinearColor(0.62F, 0.17F, 0.08F);
    case ETerraRealitySliceElementKind::MarketStall: return FLinearColor(0.37F, 0.20F, 0.09F);
    case ETerraRealitySliceElementKind::Well: return FLinearColor(0.31F, 0.35F, 0.37F);
    case ETerraRealitySliceElementKind::Wall: return FLinearColor(0.49F, 0.39F, 0.27F);
    case ETerraRealitySliceElementKind::Gate: return FLinearColor(0.43F, 0.30F, 0.17F);
    case ETerraRealitySliceElementKind::Courtyard: return FLinearColor(0.24F, 0.20F, 0.12F);
    case ETerraRealitySliceElementKind::PublicSpace: return FLinearColor(0.39F, 0.32F, 0.20F);
    default: return FLinearColor::Gray;
    }
}

FVector RotateLocalOffset(const FVector& LocalOffset, const float YawDeg)
{
    const float Radians = FMath::DegreesToRadians(YawDeg);
    return FVector(
        LocalOffset.X * FMath::Cos(Radians) - LocalOffset.Y * FMath::Sin(Radians),
        LocalOffset.X * FMath::Sin(Radians) + LocalOffset.Y * FMath::Cos(Radians),
        LocalOffset.Z
    );
}
} // namespace TerraRealitySliceEnvironment

ATerraRealitySliceEnvironment::ATerraRealitySliceEnvironment()
{
    PrimaryActorTick.bCanEverTick = false;
    SetReplicates(false);

    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    SceneRoot->SetMobility(EComponentMobility::Static);
    SetRootComponent(SceneRoot);

    static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(TEXT("/Engine/BasicShapes/Cube.Cube"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderFinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> MaterialFinder(
        TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial")
    );
    CubeMesh = CubeFinder.Succeeded() ? CubeFinder.Object : nullptr;
    CylinderMesh = CylinderFinder.Succeeded() ? CylinderFinder.Object : nullptr;
    BasicMaterial = MaterialFinder.Succeeded() ? MaterialFinder.Object : nullptr;

    DisclosureText = CreateDefaultSubobject<UTextRenderComponent>(TEXT("DisclosureText"));
    DisclosureText->SetupAttachment(SceneRoot);
    DisclosureText->SetRelativeLocation(FVector(0.0F, 1150.0F, 460.0F));
    DisclosureText->SetRelativeRotation(FRotator(0.0F, -90.0F, 0.0F));
    DisclosureText->SetHorizontalAlignment(EHTA_Center);
    DisclosureText->SetWorldSize(34.0F);
    DisclosureText->SetText(FText::FromString(
        TEXT("TERRA GROUND-LEVEL REALITY SLICE\nSPATIAL PROTOTYPE — FLAT ENGINEERING DATUM\nNOT PHOTOREAL")
    ));
    DisclosureText->SetTextRenderColor(FColor(235, 205, 150));

    SunLight = CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("SunLight"));
    SunLight->SetupAttachment(SceneRoot);
    SunLight->SetRelativeRotation(FRotator(-48.0F, -28.0F, 0.0F));
    SunLight->SetIntensity(7.0F);
    SunLight->SetAtmosphereSunLight(true);
    SunLight->SetMobility(EComponentMobility::Movable);

    SkyAtmosphere = CreateDefaultSubobject<USkyAtmosphereComponent>(TEXT("SkyAtmosphere"));
    SkyAtmosphere->SetupAttachment(SceneRoot);

    SkyLight = CreateDefaultSubobject<USkyLightComponent>(TEXT("SkyLight"));
    SkyLight->SetupAttachment(SceneRoot);
    SkyLight->SetIntensity(0.9F);
    SkyLight->SetRealTimeCapture(true);
    SkyLight->SetMobility(EComponentMobility::Movable);
}

UHierarchicalInstancedStaticMeshComponent* ATerraRealitySliceEnvironment::GetOrCreateBucket(
    const ETerraRealitySliceElementKind Kind,
    const bool bCollision,
    const bool bCylinder,
    TMap<int32, UHierarchicalInstancedStaticMeshComponent*>& Buckets
)
{
    const int32 Key = static_cast<int32>(Kind) * 4 + (bCollision ? 1 : 0) + (bCylinder ? 2 : 0);
    if (UHierarchicalInstancedStaticMeshComponent** Existing = Buckets.Find(Key))
    {
        return *Existing;
    }

    UStaticMesh* Mesh = bCylinder ? CylinderMesh.Get() : CubeMesh.Get();
    if (!Mesh)
    {
        return nullptr;
    }

    const FName ComponentName(*FString::Printf(TEXT("RealitySlice_%d_%s_%s"),
        static_cast<int32>(Kind),
        bCollision ? TEXT("Collision") : TEXT("Visual"),
        bCylinder ? TEXT("Cylinder") : TEXT("Box")));
    UHierarchicalInstancedStaticMeshComponent* Component = NewObject<UHierarchicalInstancedStaticMeshComponent>(this, ComponentName);
    Component->SetupAttachment(SceneRoot);
    Component->SetMobility(EComponentMobility::Static);
    Component->SetStaticMesh(Mesh);
    Component->SetGenerateOverlapEvents(false);
    Component->SetCanEverAffectNavigation(bCollision);
    Component->SetCollisionProfileName(
        bCollision ? UCollisionProfile::BlockAll_ProfileName : UCollisionProfile::NoCollision_ProfileName
    );
    Component->SetCollisionEnabled(bCollision ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
    Component->SetCastShadow(Kind != ETerraRealitySliceElementKind::Ground && Kind != ETerraRealitySliceElementKind::Road);

    if (BasicMaterial)
    {
        UMaterialInstanceDynamic* Material = UMaterialInstanceDynamic::Create(BasicMaterial, this);
        Material->SetVectorParameterValue(TEXT("Color"), TerraRealitySliceEnvironment::ColorForKind(Kind));
        Component->SetMaterial(0, Material);
        RuntimeMaterials.Add(Material);
    }

    AddInstanceComponent(Component);
    Component->RegisterComponent();
    RuntimeMeshComponents.Add(Component);
    Buckets.Add(Key, Component);
    return Component;
}

void ATerraRealitySliceEnvironment::AddBoxLikeInstance(
    const FTerraRealitySliceElement& Element,
    const bool bCylinder,
    TMap<int32, UHierarchicalInstancedStaticMeshComponent*>& Buckets
)
{
    UHierarchicalInstancedStaticMeshComponent* Component = GetOrCreateBucket(
        Element.Kind,
        Element.bCollision,
        bCylinder,
        Buckets
    );
    if (!Component)
    {
        return;
    }

    const FTransform Transform(
        FRotator(Element.PitchDeg, Element.YawDeg, 0.0F),
        Element.LocationCm,
        Element.SizeCm / 100.0
    );
    Component->AddInstance(Transform, false);
    ++RenderedInstanceCount;
}

bool ATerraRealitySliceEnvironment::AddGateInstances(
    const FTerraRealitySliceElement& Gate,
    TMap<int32, UHierarchicalInstancedStaticMeshComponent*>& Buckets,
    FString& OutError
)
{
    using namespace TerraRealitySliceEnvironment;

    const bool bAcrossY = Gate.SizeCm.Y >= Gate.SizeCm.X;
    const double Across = bAcrossY ? Gate.SizeCm.Y : Gate.SizeCm.X;
    if (Across < GateMinimumOpeningWidthCm + GateMinimumPierWidthCm * 2.0 || Gate.SizeCm.Z < 400.0)
    {
        OutError = FString::Printf(TEXT("Gate %s cannot provide a safe 6 m passage."), *Gate.ElementId);
        return false;
    }

    const double Opening = FMath::Clamp(
        Across * 0.55,
        GateMinimumOpeningWidthCm,
        Across - GateMinimumPierWidthCm * 2.0
    );
    const double PierAcross = (Across - Opening) * 0.5;
    const double Offset = Opening * 0.5 + PierAcross * 0.5;
    GateOpeningWidthCm = static_cast<float>(Opening);

    for (int32 Side = -1; Side <= 1; Side += 2)
    {
        FTerraRealitySliceElement Pier = Gate;
        Pier.ElementId = FString::Printf(TEXT("%s_runtime_pier_%d"), *Gate.ElementId, Side);
        const FVector LocalOffset = bAcrossY
            ? FVector(0.0, Side * Offset, 0.0)
            : FVector(Side * Offset, 0.0, 0.0);
        Pier.LocationCm += RotateLocalOffset(LocalOffset, Gate.YawDeg);
        if (bAcrossY)
        {
            Pier.SizeCm.Y = PierAcross;
        }
        else
        {
            Pier.SizeCm.X = PierAcross;
        }
        AddBoxLikeInstance(Pier, false, Buckets);
        ++GateCollisionPierCount;
    }

    // The lintel is a visible architectural cue, but non-colliding by design:
    // the full player capsule can traverse the portal without hidden blockers.
    const double OpeningHeight = FMath::Min(FMath::Max(360.0, Gate.SizeCm.Z * 0.58), Gate.SizeCm.Z - 80.0);
    FTerraRealitySliceElement Lintel = Gate;
    Lintel.ElementId = Gate.ElementId + TEXT("_runtime_lintel");
    Lintel.bCollision = false;
    Lintel.SizeCm.Z = Gate.SizeCm.Z - OpeningHeight;
    Lintel.LocationCm.Z = Gate.LocationCm.Z - Gate.SizeCm.Z * 0.5 + OpeningHeight + Lintel.SizeCm.Z * 0.5;
    AddBoxLikeInstance(Lintel, false, Buckets);
    return true;
}

bool ATerraRealitySliceEnvironment::BuildFromLayout(
    const FTerraRealitySliceLayout& InLayout,
    FString& OutError
)
{
    if (!UTerraRealitySliceLayoutLibrary::ValidateLayout(InLayout, OutError))
    {
        return false;
    }
    if (!CubeMesh || !CylinderMesh)
    {
        OutError = TEXT("Engine basic-shape meshes are unavailable.");
        return false;
    }

    for (UHierarchicalInstancedStaticMeshComponent* Component : RuntimeMeshComponents)
    {
        if (IsValid(Component))
        {
            Component->DestroyComponent();
        }
    }
    RuntimeMeshComponents.Reset();
    RuntimeMaterials.Reset();
    SourceElementCount = InLayout.Elements.Num();
    RenderedInstanceCount = 0;
    GateCollisionPierCount = 0;
    GateOpeningWidthCm = 0.0F;

    TMap<int32, UHierarchicalInstancedStaticMeshComponent*> Buckets;
    for (const FTerraRealitySliceElement& Element : InLayout.Elements)
    {
        if (Element.Kind == ETerraRealitySliceElementKind::Gate)
        {
            if (!AddGateInstances(Element, Buckets, OutError))
            {
                return false;
            }
            continue;
        }

        AddBoxLikeInstance(
            Element,
            Element.Kind == ETerraRealitySliceElementKind::Well,
            Buckets
        );
    }

    if (GateCollisionPierCount != 2
        || GateOpeningWidthCm < TerraRealitySliceEnvironment::GateMinimumOpeningWidthCm)
    {
        OutError = TEXT("Reality slice did not produce exactly two gate piers and a 6 m clear opening.");
        return false;
    }

    OutError.Reset();
    return true;
}
