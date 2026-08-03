#include "TerraGameModeBase.h"

#include "TerraFirstPersonCharacter.h"

ATerraGameModeBase::ATerraGameModeBase()
{
    DefaultPawnClass = ATerraFirstPersonCharacter::StaticClass();
}
