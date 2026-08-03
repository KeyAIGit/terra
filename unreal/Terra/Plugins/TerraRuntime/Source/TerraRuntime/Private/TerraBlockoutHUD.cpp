#include "TerraBlockoutHUD.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"

void ATerraBlockoutHUD::DrawHUD()
{
    Super::DrawHUD();

    if (!Canvas)
    {
        return;
    }

    constexpr float Margin = 20.0F;
    constexpr float PanelWidth = 570.0F;
    constexpr float PanelHeight = 116.0F;
    constexpr float LineHeight = 23.0F;

    DrawRect(FLinearColor(0.015F, 0.02F, 0.025F, 0.82F), Margin, Margin, PanelWidth, PanelHeight);

    UFont* Font = GEngine ? GEngine->GetSmallFont() : nullptr;
    DrawText(
        TEXT("TERRA — reality slice prototype"),
        FLinearColor(0.84F, 0.95F, 1.0F, 1.0F),
        Margin + 14.0F,
        Margin + 10.0F,
        Font,
        1.15F,
        false
    );
    DrawText(
        TEXT("STATUS: BLOCKOUT / ENGINEERING PREVIEW"),
        FLinearColor(1.0F, 0.64F, 0.18F, 1.0F),
        Margin + 14.0F,
        Margin + 10.0F + LineHeight,
        Font,
        1.0F,
        false
    );
    DrawText(
        TEXT("WASD move  |  Mouse look  |  Space jump  |  Shift sprint  |  C crouch  |  E interact"),
        FLinearColor::White,
        Margin + 14.0F,
        Margin + 10.0F + LineHeight * 2.0F,
        Font,
        0.9F,
        false
    );
    DrawText(
        TEXT("Legacy proxy geometry is a visual placeholder — not final simulation content."),
        FLinearColor(0.72F, 0.76F, 0.8F, 1.0F),
        Margin + 14.0F,
        Margin + 10.0F + LineHeight * 3.0F,
        Font,
        0.9F,
        false
    );
}
