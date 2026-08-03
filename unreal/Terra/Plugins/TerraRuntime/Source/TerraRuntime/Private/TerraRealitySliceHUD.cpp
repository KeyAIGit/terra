#include "TerraRealitySliceHUD.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"

void ATerraRealitySliceHUD::DrawHUD()
{
    Super::DrawHUD();
    if (!Canvas)
    {
        return;
    }

    constexpr float Margin = 20.0F;
    constexpr float PanelWidth = 650.0F;
    constexpr float PanelHeight = 140.0F;
    constexpr float LineHeight = 24.0F;
    DrawRect(FLinearColor(0.018F, 0.015F, 0.012F, 0.84F), Margin, Margin, PanelWidth, PanelHeight);

    UFont* Font = GEngine ? GEngine->GetSmallFont() : nullptr;
    DrawText(TEXT("TERRA — ground-level reality slice"), FLinearColor(0.94F, 0.84F, 0.65F),
        Margin + 14.0F, Margin + 10.0F, Font, 1.18F, false);
    DrawText(TEXT("STATUS: SPATIAL PROTOTYPE / BLOCKOUT"), FLinearColor(1.0F, 0.58F, 0.16F),
        Margin + 14.0F, Margin + 10.0F + LineHeight, Font, 1.0F, false);
    DrawText(TEXT("200 x 200 m audited ward | procedural massing | flat engineering datum | not photoreal"),
        FLinearColor(0.78F, 0.82F, 0.84F), Margin + 14.0F, Margin + 10.0F + LineHeight * 2.0F,
        Font, 0.9F, false);
    DrawText(TEXT("WASD move | Mouse look | Space jump | Shift sprint | C crouch | E interact"),
        FLinearColor::White, Margin + 14.0F, Margin + 10.0F + LineHeight * 3.0F,
        Font, 0.9F, false);
    DrawText(TEXT("This validates scale, routes, collision and first-person readability — not reality fidelity."),
        FLinearColor(0.70F, 0.72F, 0.73F), Margin + 14.0F, Margin + 10.0F + LineHeight * 4.0F,
        Font, 0.9F, false);
}
