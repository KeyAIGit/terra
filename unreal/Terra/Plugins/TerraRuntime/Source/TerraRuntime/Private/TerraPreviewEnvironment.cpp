#include "TerraPreviewEnvironment.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "UObject/ConstructorHelpers.h"

ATerraPreviewEnvironment::ATerraPreviewEnvironment()
{
    PrimaryActorTick.bCanEverTick = false;
    SetReplicates(false);

    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    SceneRoot->SetMobility(EComponentMobility::Static);
    SetRootComponent(SceneRoot);

    static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(TEXT("/Engine/BasicShapes/Cube.Cube"));
    UStaticMesh* CubeMesh = CubeFinder.Succeeded() ? CubeFinder.Object : nullptr;

    Ground = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Ground"));
    Ground->SetupAttachment(SceneRoot);
    Ground->SetStaticMesh(CubeMesh);
    Ground->SetRelativeLocation(FVector(0.0F, 0.0F, -10.0F));
    Ground->SetRelativeScale3D(FVector(80.0F, 80.0F, 0.2F));
    Ground->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
    Ground->SetGenerateOverlapEvents(false);
    Ground->SetMobility(EComponentMobility::Static);

    NearMarker = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("NearMarker"));
    NearMarker->SetupAttachment(SceneRoot);
    NearMarker->SetStaticMesh(CubeMesh);
    NearMarker->SetRelativeLocation(FVector(900.0F, -350.0F, 100.0F));
    NearMarker->SetRelativeScale3D(FVector(1.0F, 1.0F, 2.0F));
    NearMarker->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
    NearMarker->SetMobility(EComponentMobility::Static);

    FarMarker = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("FarMarker"));
    FarMarker->SetupAttachment(SceneRoot);
    FarMarker->SetStaticMesh(CubeMesh);
    FarMarker->SetRelativeLocation(FVector(1500.0F, 450.0F, 175.0F));
    FarMarker->SetRelativeScale3D(FVector(1.5F, 1.5F, 3.5F));
    FarMarker->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
    FarMarker->SetMobility(EComponentMobility::Static);

    DisclosureText = CreateDefaultSubobject<UTextRenderComponent>(TEXT("DisclosureText"));
    DisclosureText->SetupAttachment(SceneRoot);
    DisclosureText->SetRelativeLocation(FVector(750.0F, 0.0F, 260.0F));
    DisclosureText->SetRelativeRotation(FRotator(0.0F, 180.0F, 0.0F));
    DisclosureText->SetHorizontalAlignment(EHTA_Center);
    DisclosureText->SetWorldSize(32.0F);
    DisclosureText->SetText(FText::FromString(TEXT("TERRA ENGINEERING PREVIEW\nSIMPLE COLLISION TEST PAD\nSTATUS: BLOCKOUT")));
    DisclosureText->SetTextRenderColor(FColor(195, 230, 255));

    SunLight = CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("SunLight"));
    SunLight->SetupAttachment(SceneRoot);
    SunLight->SetRelativeRotation(FRotator(-50.0F, -35.0F, 0.0F));
    SunLight->SetIntensity(8.0F);
    SunLight->SetAtmosphereSunLight(true);
    SunLight->SetMobility(EComponentMobility::Movable);

    SkyAtmosphere = CreateDefaultSubobject<USkyAtmosphereComponent>(TEXT("SkyAtmosphere"));
    SkyAtmosphere->SetupAttachment(SceneRoot);

    SkyLight = CreateDefaultSubobject<USkyLightComponent>(TEXT("SkyLight"));
    SkyLight->SetupAttachment(SceneRoot);
    SkyLight->SetIntensity(1.0F);
    SkyLight->SetRealTimeCapture(true);
    SkyLight->SetMobility(EComponentMobility::Movable);
}
