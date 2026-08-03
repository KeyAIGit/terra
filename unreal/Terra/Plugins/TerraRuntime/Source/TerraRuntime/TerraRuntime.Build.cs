using UnrealBuildTool;

public class TerraRuntime : ModuleRules
{
    public TerraRuntime(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(
            new[]
            {
                "Core",
                "CoreUObject",
                "Engine",
                "InputCore"
            }
        );

        PrivateDependencyModuleNames.AddRange(
            new[]
            {
                "Json",
                "JsonUtilities"
            }
        );
    }
}
