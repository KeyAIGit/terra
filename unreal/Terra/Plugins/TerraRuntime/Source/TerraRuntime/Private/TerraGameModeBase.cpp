#include "TerraGameModeBase.h"

#include "TerraBlockoutHUD.h"
#include "TerraFirstPersonCharacter.h"

ATerraGameModeBase::ATerraGameModeBase()
{
    DefaultPawnClass = ATerraFirstPersonCharacter::StaticClass();
    HUDClass = ATerraBlockoutHUD::StaticClass();
}
