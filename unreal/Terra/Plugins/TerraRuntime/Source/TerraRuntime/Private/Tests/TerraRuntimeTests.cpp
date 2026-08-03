#if WITH_DEV_AUTOMATION_TESTS

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/HitResult.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Misc/AutomationTest.h"
#include "Misc/Paths.h"
#include "Tests/AutomationCommon.h"

#include "JsonObjectConverter.h"
#include "TerraBlockoutHUD.h"
#include "TerraFirstPersonCharacter.h"
#include "TerraGameModeBase.h"
#include "TerraInteractionComponent.h"
#include "TerraPreviewEnvironment.h"
#include "TerraPreviewGameMode.h"
#include "TerraRealitySliceEnvironment.h"
#include "TerraRealitySliceGameMode.h"
#include "TerraRealitySliceHUD.h"
#include "TerraRealitySliceLayout.h"
#include "TerraSimulationTypes.h"

#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FTerraSceneJsonRoundTripTest,
    "Terra.Runtime.Data.SceneJsonRoundTrip",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::SmokeFilter
)

bool FTerraSceneJsonRoundTripTest::RunTest(const FString& Parameters)
{
    FTerraSceneDefinition Source;
    Source.SceneId = FGuid::NewGuid();
    Source.SimulationRunId = TEXT("automation-seed-42");
    Source.SimulationTick = 987654;
    Source.CalendarYear = 500;
    Source.EraId = TEXT("late-antiquity");
    Source.RegionId = TEXT("test-region");
    Source.GeographicOrigin.Latitude = 41.2995;
    Source.GeographicOrigin.Longitude = 69.2401;
    Source.Authority = ETerraDataAuthority::Known;
    Source.Metadata.Add(FName(TEXT("source")), TEXT("automation"));

    FTerraNPCDefinition Person;
    Person.PersonId = FGuid::NewGuid();
    Person.DisplayName = FText::FromString(TEXT("Amina"));
    Person.CultureId = TEXT("test-culture");
    Person.PrimaryLanguageId = TEXT("test-language");
    Person.OccupationId = TEXT("potter");
    Person.BirthYear = 477;
    Person.TraitIds = {FName(TEXT("curious")), FName(TEXT("patient"))};
    Person.Authority = ETerraDataAuthority::Typical;
    Source.Population.Add(Person);

    FTerraNPCRuntimeState State;
    State.PersonId = Person.PersonId;
    State.LastSimulationTick = Source.SimulationTick;
    State.CurrentActivityId = FName(TEXT("working"));

    FTerraNeedState Need;
    Need.NeedId = FName(TEXT("rest"));
    Need.Satisfaction = 0.625F;
    Need.ChangePerSimulatedHour = -0.02F;
    State.Needs.Add(Need);

    FTerraMemoryRecord Memory;
    Memory.MemoryId = FGuid::NewGuid();
    Memory.EventType = FName(TEXT("met_player"));
    Memory.Summary = TEXT("Met the player near the workshop.");
    Memory.SimulationTick = Source.SimulationTick;
    Memory.EmotionalWeight = 0.4F;
    State.Memories.Add(Memory);
    Source.InitialPopulationState.Add(State);

    FString Json;
    if (!TestTrue(TEXT("Scene serializes to JSON"), FJsonObjectConverter::UStructToJsonObjectString(Source, Json)))
    {
        return false;
    }

    FTerraSceneDefinition Restored;
    if (!TestTrue(TEXT("Scene deserializes from JSON"), FJsonObjectConverter::JsonObjectStringToUStruct(Json, &Restored)))
    {
        return false;
    }

    TestEqual(TEXT("Scene id survives"), Restored.SceneId, Source.SceneId);
    TestEqual(TEXT("Run id survives"), Restored.SimulationRunId, Source.SimulationRunId);
    TestEqual(TEXT("Simulation tick survives"), Restored.SimulationTick, Source.SimulationTick);
    TestTrue(TEXT("Authority survives"), Restored.Authority == ETerraDataAuthority::Known);
    TestEqual(TEXT("Population count survives"), Restored.Population.Num(), 1);
    TestEqual(TEXT("State count survives"), Restored.InitialPopulationState.Num(), 1);

    if (Restored.Population.Num() == 1 && Restored.InitialPopulationState.Num() == 1)
    {
        TestEqual(TEXT("Person id survives"), Restored.Population[0].PersonId, Person.PersonId);
        TestTrue(TEXT("Person authority survives"), Restored.Population[0].Authority == ETerraDataAuthority::Typical);
        TestEqual(TEXT("Need count survives"), Restored.InitialPopulationState[0].Needs.Num(), 1);

        if (Restored.InitialPopulationState[0].Needs.Num() == 1)
        {
            TestTrue(
                TEXT("Need value survives"),
                FMath::IsNearlyEqual(Restored.InitialPopulationState[0].Needs[0].Satisfaction, Need.Satisfaction)
            );
        }
    }

    return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FTerraGameplayDefaultsTest,
    "Terra.Runtime.Gameplay.Defaults",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::SmokeFilter
)

bool FTerraGameplayDefaultsTest::RunTest(const FString& Parameters)
{
    const ATerraGameModeBase* GameMode = GetDefault<ATerraGameModeBase>();
    TestNotNull(TEXT("Game mode CDO exists"), GameMode);

    if (GameMode)
    {
        TestEqual(
            TEXT("Game mode selects Terra first-person pawn"),
            GameMode->DefaultPawnClass.Get(),
            ATerraFirstPersonCharacter::StaticClass()
        );
        TestEqual(
            TEXT("Game mode discloses blockout status through its HUD"),
            GameMode->HUDClass.Get(),
            ATerraBlockoutHUD::StaticClass()
        );
    }

    const ATerraPreviewGameMode* PreviewGameMode = GetDefault<ATerraPreviewGameMode>();
    TestNotNull(TEXT("Asset-independent preview game mode CDO exists"), PreviewGameMode);

    const ATerraRealitySliceGameMode* RealitySliceGameMode = GetDefault<ATerraRealitySliceGameMode>();
    TestNotNull(TEXT("Reality-slice game mode CDO exists"), RealitySliceGameMode);
    if (RealitySliceGameMode)
    {
        TestEqual(
            TEXT("Reality-slice mode uses an explicit spatial-prototype HUD"),
            RealitySliceGameMode->HUDClass.Get(),
            ATerraRealitySliceHUD::StaticClass()
        );
    }

    const ATerraFirstPersonCharacter* Character = GetDefault<ATerraFirstPersonCharacter>();
    TestNotNull(TEXT("Character CDO exists"), Character);

    if (Character)
    {
        TestNotNull(TEXT("Character owns a camera"), Character->GetFirstPersonCamera());
        TestNotNull(TEXT("Character owns an interaction component"), Character->GetInteractionComponent());
        TestTrue(TEXT("Initial mouse capture has a short guard window"), Character->InitialMouseLookDelay > 0.0F);
        TestTrue(TEXT("Mouse look spike limit is positive"), Character->MaxMouseLookInputPerFrame > 0.0F);
    }

    TestEqual(
        TEXT("Positive look spike is clamped"),
        ATerraFirstPersonCharacter::SanitizeLookInput(500.0F, 8.0F),
        8.0F
    );
    TestEqual(
        TEXT("Negative look spike is clamped"),
        ATerraFirstPersonCharacter::SanitizeLookInput(-500.0F, 8.0F),
        -8.0F
    );
    TestEqual(
        TEXT("Non-finite look input is discarded"),
        ATerraFirstPersonCharacter::SanitizeLookInput(std::numeric_limits<float>::quiet_NaN(), 8.0F),
        0.0F
    );

    const UTerraInteractionComponent* Interaction = GetDefault<UTerraInteractionComponent>();
    TestNotNull(TEXT("Interaction component CDO exists"), Interaction);

    if (Interaction)
    {
        TestTrue(TEXT("Interaction has positive reach"), Interaction->InteractionDistance > 0.0F);
        TestTrue(TEXT("Interaction component replicates by default"), Interaction->GetIsReplicated());
        TestNull(TEXT("Interaction starts without focus"), Interaction->GetFocusedActor());
        TestTrue(TEXT("Interaction starts without a prompt"), Interaction->GetActivePrompt().IsEmpty());
    }

    return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FTerraGroundLevelPreviewTest,
    "Terra.Runtime.Gameplay.GroundLevelPreview",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter
)

bool FTerraGroundLevelPreviewTest::RunTest(const FString& Parameters)
{
    FTestWorldWrapper WorldWrapper;
    if (!TestTrue(TEXT("Transient game world is created"), WorldWrapper.CreateTestWorld(EWorldType::Game)))
    {
        WorldWrapper.ForwardErrorMessages(this);
        return false;
    }

    UWorld* World = WorldWrapper.GetTestWorld();
    if (!TestNotNull(TEXT("Transient game world exists"), World))
    {
        WorldWrapper.ForwardErrorMessages(this);
        return false;
    }

    if (!TestTrue(TEXT("Transient game world begins play"), WorldWrapper.BeginPlayInTestWorld()))
    {
        WorldWrapper.ForwardErrorMessages(this);
        return false;
    }

    FActorSpawnParameters SpawnParameters;
    SpawnParameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    SpawnParameters.ObjectFlags |= RF_Transient;

    ATerraPreviewEnvironment* Environment = World->SpawnActor<ATerraPreviewEnvironment>(
        ATerraPreviewEnvironment::StaticClass(),
        FTransform::Identity,
        SpawnParameters
    );
    TestNotNull(TEXT("Preview collision test pad spawns"), Environment);
    if (!Environment)
    {
        WorldWrapper.ForwardErrorMessages(this);
        return false;
    }

    FTransform StartTransform = ATerraPreviewGameMode::GetPreviewStartTransform();
    StartTransform.SetRotation(FRotator(0.0F, 37.0F, 0.0F).Quaternion());
    ATerraFirstPersonCharacter* Character = World->SpawnActor<ATerraFirstPersonCharacter>(
        ATerraFirstPersonCharacter::StaticClass(),
        StartTransform,
        SpawnParameters
    );
    TestNotNull(TEXT("Terra pawn spawns above the pad"), Character);

    APlayerController* PlayerController = World->SpawnActor<APlayerController>(
        APlayerController::StaticClass(),
        FTransform::Identity,
        SpawnParameters
    );
    TestNotNull(TEXT("Test player controller spawns"), PlayerController);

    if (!Character || !PlayerController)
    {
        WorldWrapper.ForwardErrorMessages(this);
        return false;
    }

    PlayerController->SetControlRotation(FRotator(78.0F, -120.0F, 15.0F));
    PlayerController->Possess(Character);
    WorldWrapper.TickTestWorld(1.0F / 60.0F);

    const FRotator StabilizedRotation = PlayerController->GetControlRotation();
    TestTrue(TEXT("Initial view pitch is reset"), FMath::IsNearlyZero(StabilizedRotation.Pitch, 0.01F));
    TestTrue(TEXT("Initial view roll is reset"), FMath::IsNearlyZero(StabilizedRotation.Roll, 0.01F));
    TestTrue(TEXT("Initial view keeps PlayerStart yaw"), FMath::IsNearlyEqual(StabilizedRotation.Yaw, 37.0F, 0.01F));

    const UCameraComponent* Camera = Character->GetFirstPersonCamera();
    TestNotNull(TEXT("Runtime camera remains attached"), Camera);
    if (Camera)
    {
        TestTrue(TEXT("Camera begins with a level forward vector"), FMath::Abs(Camera->GetForwardVector().Z) < 0.02F);
        TestTrue(TEXT("Camera is above ground level"), Camera->GetComponentLocation().Z > 120.0F);
    }

    FHitResult FloorHit;
    FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(TerraPreviewAutomationFloor), false, Character);
    const bool bHitFloor = World->LineTraceSingleByChannel(
        FloorHit,
        FVector(0.0F, 0.0F, 500.0F),
        FVector(0.0F, 0.0F, -500.0F),
        ECC_Visibility,
        QueryParams
    );
    TestTrue(TEXT("Preview floor blocks a runtime trace"), bHitFloor);
    if (bHitFloor)
    {
        TestTrue(TEXT("Preview floor top is at ground level"), FMath::IsNearlyZero(FloorHit.ImpactPoint.Z, 1.0F));
        TestEqual(
            TEXT("Trace hits the dedicated preview ground"),
            FloorHit.GetComponent(),
            static_cast<UPrimitiveComponent*>(Environment->GetGround())
        );
    }

    const UCapsuleComponent* Capsule = Character->GetCapsuleComponent();
    if (Capsule)
    {
        const float InitialBottom = StartTransform.GetLocation().Z - Capsule->GetScaledCapsuleHalfHeight();
        TestTrue(TEXT("Preview spawn begins clear of the floor"), InitialBottom > 0.0F);
        TestTrue(TEXT("Preview spawn is close enough to settle quickly"), InitialBottom < 30.0F);
    }

    WorldWrapper.ForwardErrorMessages(this);
    return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FTerraRealitySliceLayoutContractTest,
    "Terra.Runtime.RealitySlice.LayoutContract",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::SmokeFilter
)

bool FTerraRealitySliceLayoutContractTest::RunTest(const FString& Parameters)
{
    FTerraRealitySliceLayout Layout;
    FString Error;
    const FString RuntimePath = UTerraRealitySliceLayoutLibrary::GetGeneratedRuntimeLayoutPath();
    if (!TestTrue(
        TEXT("Generated runtime adapter loads and validates"),
        UTerraRealitySliceLayoutLibrary::LoadLayoutFromJsonFile(RuntimePath, Layout, Error)
    ))
    {
        AddError(Error);
        return false;
    }

    TestEqual(TEXT("Audited ward id survives"), Layout.LayoutId, FString(TEXT("raflir-south-gate-market-ward-v1")));
    TestTrue(TEXT("Ward width is 200 m"), FMath::IsNearlyEqual(Layout.ExtentCm.X, 20000.0, 0.1));
    TestTrue(TEXT("Ward height is 200 m"), FMath::IsNearlyEqual(Layout.ExtentCm.Y, 20000.0, 0.1));
    TestTrue(TEXT("Source XY anchor is retained for audit"),
        Layout.SourceAnchorCm.Equals(FVector(0.0, -7200.0, 245.292), 0.01));
    TestEqual(TEXT("Adapter plus runtime public-square hint yields 543 elements"), Layout.Elements.Num(), 543);
    TestTrue(TEXT("Unsafe slab-edge source spawn is relocated"), Layout.bPlayerStartRelocated);
    TestTrue(TEXT("Relocated spawn uses the flat engineering datum"),
        FMath::IsNearlyEqual(Layout.PlayerStart.LocationCm.Z, 120.0, 0.01));

    TMap<ETerraRealitySliceElementKind, int32> Counts;
    const FTerraRealitySliceElement* Ground = nullptr;
    const FTerraRealitySliceElement* Gate = nullptr;
    for (const FTerraRealitySliceElement& Element : Layout.Elements)
    {
        Counts.FindOrAdd(Element.Kind) += 1;
        if (Element.Kind == ETerraRealitySliceElementKind::Ground) Ground = &Element;
        if (Element.Kind == ETerraRealitySliceElementKind::Gate) Gate = &Element;
        if (Element.Kind == ETerraRealitySliceElementKind::Building
            || Element.Kind == ETerraRealitySliceElementKind::MarketStall
            || Element.Kind == ETerraRealitySliceElementKind::Well
            || Element.Kind == ETerraRealitySliceElementKind::Wall
            || Element.Kind == ETerraRealitySliceElementKind::Gate)
        {
            TestTrue(
                FString::Printf(TEXT("Ground-contact element %s is snapped to z=0"), *Element.ElementId),
                FMath::IsNearlyZero(Element.LocationCm.Z - Element.SizeCm.Z * 0.5, 0.01)
            );
        }
    }

    TestEqual(TEXT("Runtime adapter has 94 building masses"), Counts.FindRef(ETerraRealitySliceElementKind::Building), 94);
    TestEqual(TEXT("Runtime adapter has 33 road segments"), Counts.FindRef(ETerraRealitySliceElementKind::Road), 33);
    TestEqual(TEXT("Runtime adapter has 99 doors"), Counts.FindRef(ETerraRealitySliceElementKind::Door), 99);
    TestEqual(TEXT("Runtime adapter has 188 windows"), Counts.FindRef(ETerraRealitySliceElementKind::Window), 188);
    TestEqual(TEXT("Runtime adapter has four market stalls"), Counts.FindRef(ETerraRealitySliceElementKind::MarketStall), 4);
    TestEqual(TEXT("Runtime adapter has exactly one gate"), Counts.FindRef(ETerraRealitySliceElementKind::Gate), 1);
    TestNotNull(TEXT("Flat-datum ground exists"), Ground);
    if (Ground)
    {
        TestTrue(TEXT("Ground top is exactly z=0"),
            FMath::IsNearlyZero(Ground->LocationCm.Z + Ground->SizeCm.Z * 0.5, 0.01));
    }
    TestNotNull(TEXT("Gate contract exists"), Gate);

    FString SpawnReason;
    TestTrue(TEXT("Relocated PlayerStart passes capsule/road-footprint validation"),
        UTerraRealitySliceLayoutLibrary::IsPlayerStartClear(Layout, Layout.PlayerStart.LocationCm, SpawnReason));

    FTerraRealitySliceLayout InjectedUnsafeLayout = Layout;
    if (Gate)
    {
        InjectedUnsafeLayout.PlayerStart.LocationCm = Gate->LocationCm;
        TestFalse(TEXT("Gate mass cannot be accepted blindly as a spawn"),
            UTerraRealitySliceLayoutLibrary::IsPlayerStartClear(
                InjectedUnsafeLayout,
                InjectedUnsafeLayout.PlayerStart.LocationCm,
                SpawnReason
            ));
        TestTrue(TEXT("Injected unsafe spawn is deterministically relocated"),
            UTerraRealitySliceLayoutLibrary::ResolveSafePlayerStart(InjectedUnsafeLayout, SpawnReason));
        TestTrue(TEXT("Relocated injected spawn validates"),
            UTerraRealitySliceLayoutLibrary::ValidateLayout(InjectedUnsafeLayout, Error));
    }

    FTerraRealitySliceLayout Fallback = UTerraRealitySliceLayoutLibrary::MakeSafeFallbackLayout();
    TestTrue(TEXT("Embedded fallback validates independently"),
        UTerraRealitySliceLayoutLibrary::ValidateLayout(Fallback, Error));

    FTerraRealitySliceLayout RichLayout;
    const FString RichPath = FPaths::Combine(
        FPaths::ProjectDir(),
        TEXT("Scripts/terra_data/generated/reality_slice_capital.json")
    );
    TestTrue(TEXT("Rich audited schema converts through the permissive runtime bridge"),
        UTerraRealitySliceLayoutLibrary::LoadLayoutFromJsonFile(RichPath, RichLayout, Error));
    TestEqual(TEXT("Rich bridge preserves the audited ward id"), RichLayout.LayoutId, Layout.LayoutId);
    int32 RichCourtyardCount = 0;
    int32 RichRoadSegmentCount = 0;
    for (const FTerraRealitySliceElement& Element : RichLayout.Elements)
    {
        RichCourtyardCount += Element.Kind == ETerraRealitySliceElementKind::Courtyard ? 1 : 0;
        RichRoadSegmentCount += Element.Kind == ETerraRealitySliceElementKind::Road ? 1 : 0;
    }
    TestEqual(TEXT("Rich bridge includes four explicit courtyards"), RichCourtyardCount, 4);
    TestEqual(TEXT("Rich bridge converts six roads plus 27 service paths"), RichRoadSegmentCount, 33);
    TestTrue(TEXT("Rich bridge also resolves to a safe pedestrian spawn"),
        UTerraRealitySliceLayoutLibrary::IsPlayerStartClear(
            RichLayout,
            RichLayout.PlayerStart.LocationCm,
            SpawnReason
        ));
    return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FTerraRealitySliceGroundNavigationTest,
    "Terra.Runtime.RealitySlice.GroundNavigation",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter
)

bool FTerraRealitySliceGroundNavigationTest::RunTest(const FString& Parameters)
{
    FTerraRealitySliceLayout Layout;
    FString Error;
    if (!TestTrue(
        TEXT("Audited runtime layout loads for navigation test"),
        UTerraRealitySliceLayoutLibrary::LoadLayoutFromJsonFile(
            UTerraRealitySliceLayoutLibrary::GetGeneratedRuntimeLayoutPath(),
            Layout,
            Error
        )
    ))
    {
        AddError(Error);
        return false;
    }

    FTestWorldWrapper WorldWrapper;
    if (!TestTrue(TEXT("Reality-slice test world is created"), WorldWrapper.CreateTestWorld(EWorldType::Game)))
    {
        WorldWrapper.ForwardErrorMessages(this);
        return false;
    }
    UWorld* World = WorldWrapper.GetTestWorld();
    if (!TestNotNull(TEXT("Reality-slice test world exists"), World)
        || !TestTrue(TEXT("Reality-slice test world begins play"), WorldWrapper.BeginPlayInTestWorld()))
    {
        WorldWrapper.ForwardErrorMessages(this);
        return false;
    }

    FActorSpawnParameters SpawnParameters;
    SpawnParameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    SpawnParameters.ObjectFlags |= RF_Transient;
    ATerraRealitySliceEnvironment* Environment = World->SpawnActor<ATerraRealitySliceEnvironment>(
        ATerraRealitySliceEnvironment::StaticClass(),
        FTransform::Identity,
        SpawnParameters
    );
    if (!TestNotNull(TEXT("Procedural ward environment spawns"), Environment)
        || !TestTrue(TEXT("Procedural ward builds from validated JSON"), Environment->BuildFromLayout(Layout, Error)))
    {
        AddError(Error);
        WorldWrapper.ForwardErrorMessages(this);
        return false;
    }

    TestEqual(TEXT("One source gate becomes two piers plus one lintel"),
        Environment->GetRenderedInstanceCount(), Layout.Elements.Num() + 2);
    TestEqual(TEXT("Gate has exactly two colliding piers"), Environment->GetGateCollisionPierCount(), 2);
    TestTrue(TEXT("Gate opening is at least 6 m"), Environment->GetGateOpeningWidthCm() >= 600.0F);

    const FTerraRealitySliceElement* Gate = Layout.Elements.FindByPredicate([](const FTerraRealitySliceElement& Element)
    {
        return Element.Kind == ETerraRealitySliceElementKind::Gate;
    });
    TestNotNull(TEXT("Navigation test finds the gate"), Gate);
    if (Gate)
    {
        const float Radians = FMath::DegreesToRadians(Gate->YawDeg);
        const FVector LocalForward(FMath::Cos(Radians), FMath::Sin(Radians), 0.0F);
        const FVector LocalRight(-FMath::Sin(Radians), FMath::Cos(Radians), 0.0F);
        const bool bAcrossY = Gate->SizeCm.Y >= Gate->SizeCm.X;
        const FVector AcrossDirection = bAcrossY ? LocalRight : LocalForward;
        const FVector ThroughDirection = bAcrossY ? LocalForward : LocalRight;
        const double Across = bAcrossY ? Gate->SizeCm.Y : Gate->SizeCm.X;
        const double Depth = bAcrossY ? Gate->SizeCm.X : Gate->SizeCm.Y;
        const FVector PassageCenter(Gate->LocationCm.X, Gate->LocationCm.Y, 120.0);

        FCollisionQueryParams GateParams(SCENE_QUERY_STAT(TerraRealitySliceGate), false);
        FHitResult ThroughHit;
        const bool bPassageBlocked = World->LineTraceSingleByChannel(
            ThroughHit,
            PassageCenter - ThroughDirection * (Depth * 0.75),
            PassageCenter + ThroughDirection * (Depth * 0.75),
            ECC_Pawn,
            GateParams
        );
        TestFalse(TEXT("Gate center is a physically open route at player height"), bPassageBlocked);

        FHitResult AcrossHit;
        const bool bPierHit = World->LineTraceSingleByChannel(
            AcrossHit,
            PassageCenter - AcrossDirection * (Across * 0.6),
            PassageCenter + AcrossDirection * (Across * 0.6),
            ECC_Pawn,
            GateParams
        );
        TestTrue(TEXT("Cross-gate trace hits a structural collision pier"), bPierHit);
    }

    const double MainStreetWaypointsY[] = {-8000.0, -4000.0, 0.0, 4000.0, 8000.0};
    for (const double Y : MainStreetWaypointsY)
    {
        const FVector CapsuleCenter(0.0, Y, 120.0);
        const bool bBlocked = World->OverlapBlockingTestByChannel(
            CapsuleCenter,
            FQuat::Identity,
            ECC_Pawn,
            FCollisionShape::MakeCapsule(42.0F, 96.0F)
        );
        TestFalse(FString::Printf(TEXT("Main avenue capsule is clear at y=%.0f"), Y), bBlocked);

        FHitResult FloorHit;
        const bool bFloorHit = World->LineTraceSingleByChannel(
            FloorHit,
            FVector(0.0, Y, 500.0),
            FVector(0.0, Y, -100.0),
            ECC_Visibility
        );
        TestTrue(FString::Printf(TEXT("Main avenue has walkable floor at y=%.0f"), Y), bFloorHit);
        if (bFloorHit)
        {
            TestTrue(TEXT("Flat-datum floor remains within an 8 cm road finish"),
                FloorHit.ImpactPoint.Z >= -0.1 && FloorHit.ImpactPoint.Z <= 8.1);
        }
    }

    ATerraFirstPersonCharacter* Character = World->SpawnActor<ATerraFirstPersonCharacter>(
        ATerraFirstPersonCharacter::StaticClass(),
        FTransform(FRotator(0.0F, Layout.PlayerStart.YawDeg, 0.0F), Layout.PlayerStart.LocationCm),
        SpawnParameters
    );
    APlayerController* PlayerController = World->SpawnActor<APlayerController>(
        APlayerController::StaticClass(),
        FTransform::Identity,
        SpawnParameters
    );
    if (TestNotNull(TEXT("Ground-level pawn spawns"), Character)
        && TestNotNull(TEXT("Ground-level controller spawns"), PlayerController))
    {
        PlayerController->Possess(Character);
        WorldWrapper.TickTestWorld(1.0F / 60.0F);
        const UCameraComponent* Camera = Character->GetFirstPersonCamera();
        TestNotNull(TEXT("Reality-slice pawn retains first-person camera"), Camera);
        if (Camera)
        {
            TestTrue(TEXT("Reality-slice camera begins level"), FMath::Abs(Camera->GetForwardVector().Z) < 0.02F);
        }
    }

    WorldWrapper.ForwardErrorMessages(this);
    return !HasAnyErrors();
}

#endif // WITH_DEV_AUTOMATION_TESTS
