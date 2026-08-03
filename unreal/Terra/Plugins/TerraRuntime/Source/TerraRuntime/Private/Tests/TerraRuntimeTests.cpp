#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"

#include "JsonObjectConverter.h"
#include "TerraFirstPersonCharacter.h"
#include "TerraGameModeBase.h"
#include "TerraInteractionComponent.h"
#include "TerraSimulationTypes.h"

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
    }

    const ATerraFirstPersonCharacter* Character = GetDefault<ATerraFirstPersonCharacter>();
    TestNotNull(TEXT("Character CDO exists"), Character);

    if (Character)
    {
        TestNotNull(TEXT("Character owns a camera"), Character->GetFirstPersonCamera());
        TestNotNull(TEXT("Character owns an interaction component"), Character->GetInteractionComponent());
    }

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

#endif // WITH_DEV_AUTOMATION_TESTS
