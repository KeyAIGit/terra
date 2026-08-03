#include "TerraRealitySliceLayout.h"

#include "Dom/JsonObject.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/Parse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

#include <cfloat>

namespace TerraRealitySliceLayout
{
constexpr int32 RuntimeSchemaVersion = 1;
constexpr int32 MaxRuntimeElements = 2000;
constexpr double PlayerCapsuleRadiusCm = 42.0;
constexpr double PlayerCapsuleHalfHeightCm = 96.0;
constexpr double PlayerSpawnCenterZCm = 120.0;
constexpr double GateMinimumOpeningWidthCm = 600.0;
constexpr double GateMinimumPierWidthCm = 120.0;

bool IsFiniteVector(const FVector& Vector)
{
    return FMath::IsFinite(Vector.X) && FMath::IsFinite(Vector.Y) && FMath::IsFinite(Vector.Z);
}

TSharedPtr<FJsonObject> GetObject(const TSharedPtr<FJsonObject>& Parent, const TCHAR* Field)
{
    if (!Parent)
    {
        return nullptr;
    }

    const TSharedPtr<FJsonObject>* Value = nullptr;
    return Parent->TryGetObjectField(Field, Value) && Value ? *Value : nullptr;
}

const TArray<TSharedPtr<FJsonValue>>* GetArray(const TSharedPtr<FJsonObject>& Parent, const TCHAR* Field)
{
    if (!Parent)
    {
        return nullptr;
    }

    const TArray<TSharedPtr<FJsonValue>>* Value = nullptr;
    return Parent->TryGetArrayField(Field, Value) ? Value : nullptr;
}

bool ReadVector(const TSharedPtr<FJsonValue>& Value, FVector& OutVector)
{
    if (!Value.IsValid())
    {
        return false;
    }

    if (Value->Type == EJson::Object)
    {
        const TSharedPtr<FJsonObject> Object = Value->AsObject();
        double X = 0.0;
        double Y = 0.0;
        double Z = 0.0;
        if (!Object || !Object->TryGetNumberField(TEXT("x"), X) || !Object->TryGetNumberField(TEXT("y"), Y))
        {
            return false;
        }
        Object->TryGetNumberField(TEXT("z"), Z);
        OutVector = FVector(X, Y, Z);
        return IsFiniteVector(OutVector);
    }

    if (Value->Type == EJson::Array)
    {
        const TArray<TSharedPtr<FJsonValue>>& Values = Value->AsArray();
        if (Values.Num() < 2 || Values[0]->Type != EJson::Number || Values[1]->Type != EJson::Number)
        {
            return false;
        }

        const double Z = Values.Num() >= 3 && Values[2]->Type == EJson::Number ? Values[2]->AsNumber() : 0.0;
        OutVector = FVector(Values[0]->AsNumber(), Values[1]->AsNumber(), Z);
        return IsFiniteVector(OutVector);
    }

    return false;
}

bool ReadVectorField(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field, FVector& OutVector)
{
    if (!Object || !Object->HasField(Field))
    {
        return false;
    }
    return ReadVector(Object->TryGetField(Field), OutVector);
}

float ReadFloat(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field, const float DefaultValue = 0.0F)
{
    double Value = DefaultValue;
    return Object && Object->TryGetNumberField(Field, Value) && FMath::IsFinite(Value)
        ? static_cast<float>(Value)
        : DefaultValue;
}

bool ReadBool(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field, const bool DefaultValue)
{
    bool Value = DefaultValue;
    return Object && Object->TryGetBoolField(Field, Value) ? Value : DefaultValue;
}

bool ParseKind(const FString& InKind, ETerraRealitySliceElementKind& OutKind)
{
    const FString Kind = InKind.ToLower();
    if (Kind == TEXT("ground")) OutKind = ETerraRealitySliceElementKind::Ground;
    else if (Kind == TEXT("road")) OutKind = ETerraRealitySliceElementKind::Road;
    else if (Kind == TEXT("building")) OutKind = ETerraRealitySliceElementKind::Building;
    else if (Kind == TEXT("roof")) OutKind = ETerraRealitySliceElementKind::Roof;
    else if (Kind == TEXT("door")) OutKind = ETerraRealitySliceElementKind::Door;
    else if (Kind == TEXT("window")) OutKind = ETerraRealitySliceElementKind::Window;
    else if (Kind == TEXT("awning")) OutKind = ETerraRealitySliceElementKind::Awning;
    else if (Kind == TEXT("market_stall")) OutKind = ETerraRealitySliceElementKind::MarketStall;
    else if (Kind == TEXT("well")) OutKind = ETerraRealitySliceElementKind::Well;
    else if (Kind == TEXT("wall")) OutKind = ETerraRealitySliceElementKind::Wall;
    else if (Kind == TEXT("gate")) OutKind = ETerraRealitySliceElementKind::Gate;
    else if (Kind == TEXT("courtyard")) OutKind = ETerraRealitySliceElementKind::Courtyard;
    else if (Kind == TEXT("public_space")) OutKind = ETerraRealitySliceElementKind::PublicSpace;
    else return false;
    return true;
}

void AddElement(
    FTerraRealitySliceLayout& Layout,
    const FString& Id,
    const ETerraRealitySliceElementKind Kind,
    const FVector& Location,
    const FVector& Size,
    const float Yaw,
    const bool bCollision,
    const float Pitch = 0.0F
)
{
    FTerraRealitySliceElement& Element = Layout.Elements.AddDefaulted_GetRef();
    Element.ElementId = Id;
    Element.Kind = Kind;
    Element.LocationCm = Location;
    Element.SizeCm = Size;
    Element.YawDeg = Yaw;
    Element.PitchDeg = Pitch;
    Element.bCollision = bCollision;
}

void NormalizeXY(FTerraRealitySliceLayout& Layout, const FVector& Anchor)
{
    Layout.SourceAnchorCm = Anchor;
    Layout.PlayerStart.LocationCm.X -= Anchor.X;
    Layout.PlayerStart.LocationCm.Y -= Anchor.Y;
    for (FTerraRealitySliceElement& Element : Layout.Elements)
    {
        Element.LocationCm.X -= Anchor.X;
        Element.LocationCm.Y -= Anchor.Y;
    }
}

FString GetElementFamilyKey(const FString& ElementId)
{
    static const TCHAR* SimpleSuffixes[] = {TEXT("_body"), TEXT("_roof"), TEXT("_door"), TEXT("_awning")};
    for (const TCHAR* Suffix : SimpleSuffixes)
    {
        if (ElementId.EndsWith(Suffix))
        {
            return ElementId.LeftChop(FCString::Strlen(Suffix));
        }
    }

    int32 WindowMarker = INDEX_NONE;
    if (ElementId.FindLastChar(TEXT('_'), WindowMarker))
    {
        const int32 ExplicitWindowMarker = ElementId.Find(TEXT("_window_"), ESearchCase::CaseSensitive, ESearchDir::FromEnd);
        if (ExplicitWindowMarker != INDEX_NONE)
        {
            return ElementId.Left(ExplicitWindowMarker);
        }
    }
    return FString();
}

/**
 * The adapter samples source terrain, while this first runtime slice deliberately
 * uses one flat engineering datum. Preserve façade/roof heights relative to each
 * building base, but remove terrain undulation so no mass floats or embeds.
 */
void FlattenToEngineeringDatum(FTerraRealitySliceLayout& Layout)
{
    TMap<FString, double> FamilyBaseZ;
    for (const FTerraRealitySliceElement& Element : Layout.Elements)
    {
        if (Element.ElementId.EndsWith(TEXT("_body"))
            && (Element.Kind == ETerraRealitySliceElementKind::Building
                || Element.Kind == ETerraRealitySliceElementKind::MarketStall
                || Element.Kind == ETerraRealitySliceElementKind::Wall
                || Element.Kind == ETerraRealitySliceElementKind::Gate))
        {
            FamilyBaseZ.Add(GetElementFamilyKey(Element.ElementId), Element.LocationCm.Z - Element.SizeCm.Z * 0.5);
        }
    }

    for (FTerraRealitySliceElement& Element : Layout.Elements)
    {
        switch (Element.Kind)
        {
        case ETerraRealitySliceElementKind::Ground:
            Element.LocationCm.Z = -Element.SizeCm.Z * 0.5;
            break;
        case ETerraRealitySliceElementKind::Road:
        case ETerraRealitySliceElementKind::Building:
        case ETerraRealitySliceElementKind::MarketStall:
        case ETerraRealitySliceElementKind::Well:
        case ETerraRealitySliceElementKind::Wall:
        case ETerraRealitySliceElementKind::Gate:
        case ETerraRealitySliceElementKind::Courtyard:
        case ETerraRealitySliceElementKind::PublicSpace:
            Element.LocationCm.Z = Element.SizeCm.Z * 0.5;
            break;
        case ETerraRealitySliceElementKind::Roof:
        case ETerraRealitySliceElementKind::Door:
        case ETerraRealitySliceElementKind::Window:
        case ETerraRealitySliceElementKind::Awning:
        {
            const FString Family = GetElementFamilyKey(Element.ElementId);
            if (const double* SourceBaseZ = FamilyBaseZ.Find(Family))
            {
                Element.LocationCm.Z -= *SourceBaseZ;
            }
            else
            {
                // Rich schemas may omit a matching body. Retain only elevation
                // above the declared datum and never allow visual geometry below it.
                Element.LocationCm.Z = FMath::Max(
                    Element.SizeCm.Z * 0.5,
                    Element.LocationCm.Z - Layout.SourceAnchorCm.Z
                );
            }
            break;
        }
        default:
            break;
        }
    }

    Layout.PlayerStart.LocationCm.Z = PlayerSpawnCenterZCm;
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

bool MakeGateCollisionPiers(
    const FTerraRealitySliceElement& Gate,
    TArray<FTerraRealitySliceElement>& OutPiers,
    FString* OutError = nullptr
)
{
    const bool bAcrossY = Gate.SizeCm.Y >= Gate.SizeCm.X;
    const double Across = bAcrossY ? Gate.SizeCm.Y : Gate.SizeCm.X;
    if (Across < GateMinimumOpeningWidthCm + GateMinimumPierWidthCm * 2.0 || Gate.SizeCm.Z < 400.0)
    {
        if (OutError)
        {
            *OutError = FString::Printf(
                TEXT("Gate %s is too small for a 6 m clear passage and structural piers."),
                *Gate.ElementId
            );
        }
        return false;
    }

    const double MaxOpening = Across - GateMinimumPierWidthCm * 2.0;
    const double Opening = FMath::Clamp(Across * 0.55, GateMinimumOpeningWidthCm, MaxOpening);
    const double PierAcross = (Across - Opening) * 0.5;
    const double Offset = Opening * 0.5 + PierAcross * 0.5;

    for (int32 Side = -1; Side <= 1; Side += 2)
    {
        FTerraRealitySliceElement Pier = Gate;
        Pier.ElementId = FString::Printf(TEXT("%s_pier_%s"), *Gate.ElementId, Side < 0 ? TEXT("left") : TEXT("right"));
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
        OutPiers.Add(MoveTemp(Pier));
    }
    return true;
}

bool CircleOverlapsOrientedRect(
    const FVector& Center,
    const double Radius,
    const FTerraRealitySliceElement& Box
)
{
    const FVector Delta = Center - Box.LocationCm;
    const float Radians = FMath::DegreesToRadians(-Box.YawDeg);
    const double LocalX = Delta.X * FMath::Cos(Radians) - Delta.Y * FMath::Sin(Radians);
    const double LocalY = Delta.X * FMath::Sin(Radians) + Delta.Y * FMath::Cos(Radians);
    const double DistanceX = FMath::Max(FMath::Abs(LocalX) - Box.SizeCm.X * 0.5, 0.0);
    const double DistanceY = FMath::Max(FMath::Abs(LocalY) - Box.SizeCm.Y * 0.5, 0.0);
    return DistanceX * DistanceX + DistanceY * DistanceY <= Radius * Radius;
}

bool CapsuleOverlapsBox(const FVector& Center, const FTerraRealitySliceElement& Box)
{
    const bool bVerticalOverlap = Center.Z + PlayerCapsuleHalfHeightCm > Box.LocationCm.Z - Box.SizeCm.Z * 0.5
        && Center.Z - PlayerCapsuleHalfHeightCm < Box.LocationCm.Z + Box.SizeCm.Z * 0.5;
    return bVerticalOverlap && CircleOverlapsOrientedRect(Center, PlayerCapsuleRadiusCm, Box);
}

bool ParseRuntimeAdapter(
    const TSharedPtr<FJsonObject>& Root,
    FTerraRealitySliceLayout& OutLayout,
    FString& OutError
)
{
    double SchemaVersion = 0.0;
    if (!Root->TryGetNumberField(TEXT("schema_version"), SchemaVersion)
        || static_cast<int32>(SchemaVersion) != RuntimeSchemaVersion)
    {
        OutError = TEXT("Runtime layout requires schema_version=1.");
        return false;
    }

    OutLayout.SchemaVersion = RuntimeSchemaVersion;
    if (!Root->TryGetStringField(TEXT("layout_id"), OutLayout.LayoutId) || OutLayout.LayoutId.IsEmpty())
    {
        OutError = TEXT("Runtime layout requires layout_id.");
        return false;
    }
    Root->TryGetStringField(TEXT("title"), OutLayout.Title);

    FVector Extent;
    if (!ReadVectorField(Root, TEXT("extent_cm"), Extent) || Extent.X <= 0.0 || Extent.Y <= 0.0)
    {
        OutError = TEXT("Runtime layout requires positive extent_cm{x,y}.");
        return false;
    }
    OutLayout.ExtentCm = FVector2D(Extent.X, Extent.Y);

    const TSharedPtr<FJsonObject> PlayerStart = GetObject(Root, TEXT("player_start"));
    if (!PlayerStart || !ReadVectorField(PlayerStart, TEXT("location_cm"), OutLayout.PlayerStart.LocationCm))
    {
        OutError = TEXT("Runtime layout requires player_start.location_cm.");
        return false;
    }
    OutLayout.PlayerStart.YawDeg = ReadFloat(PlayerStart, TEXT("yaw_deg"), 90.0F);

    const TArray<TSharedPtr<FJsonValue>>* Elements = GetArray(Root, TEXT("elements"));
    if (!Elements || Elements->IsEmpty() || Elements->Num() > MaxRuntimeElements)
    {
        OutError = FString::Printf(TEXT("Runtime layout element count must be 1..%d."), MaxRuntimeElements);
        return false;
    }

    FVector Anchor = FVector::ZeroVector;
    bool bFoundGroundAnchor = false;
    for (int32 Index = 0; Index < Elements->Num(); ++Index)
    {
        if (!(*Elements)[Index].IsValid() || (*Elements)[Index]->Type != EJson::Object)
        {
            OutError = FString::Printf(TEXT("elements[%d] is not an object."), Index);
            return false;
        }
        const TSharedPtr<FJsonObject> Object = (*Elements)[Index]->AsObject();

        FString Id;
        FString KindName;
        FVector Location;
        FVector Size;
        ETerraRealitySliceElementKind Kind;
        if (!Object->TryGetStringField(TEXT("id"), Id) || Id.IsEmpty()
            || !Object->TryGetStringField(TEXT("kind"), KindName) || !ParseKind(KindName, Kind)
            || !ReadVectorField(Object, TEXT("location_cm"), Location)
            || !ReadVectorField(Object, TEXT("size_cm"), Size))
        {
            OutError = FString::Printf(TEXT("elements[%d] has invalid id/kind/location_cm/size_cm."), Index);
            return false;
        }

        AddElement(
            OutLayout,
            Id,
            Kind,
            Location,
            Size,
            ReadFloat(Object, TEXT("yaw_deg")),
            ReadBool(Object, TEXT("collision"), true),
            ReadFloat(Object, TEXT("pitch_deg"))
        );

        if (!bFoundGroundAnchor && Kind == ETerraRealitySliceElementKind::Ground)
        {
            Anchor = FVector(Location.X, Location.Y, Location.Z + Size.Z * 0.5);
            bFoundGroundAnchor = true;
        }
    }

    if (!bFoundGroundAnchor)
    {
        OutError = TEXT("Runtime layout requires one ground element so XY can be centered safely.");
        return false;
    }

    // The data adapter intentionally stays minimal. This non-colliding render
    // hint makes the audited 36x30 m civic square legible at ground level.
    AddElement(
        OutLayout,
        TEXT("E_runtime_public_square_overlay"),
        ETerraRealitySliceElementKind::PublicSpace,
        FVector(Anchor.X, Anchor.Y, Anchor.Z + 1.0),
        FVector(3600.0, 3000.0, 2.0),
        0.0F,
        false
    );

    NormalizeXY(OutLayout, Anchor);
    return true;
}

bool PolygonBounds(
    const TSharedPtr<FJsonObject>& Object,
    const TCHAR* Field,
    FVector& OutCenter,
    FVector& OutSize
)
{
    const TArray<TSharedPtr<FJsonValue>>* Points = GetArray(Object, Field);
    if (!Points || Points->Num() < 3)
    {
        return false;
    }

    FVector Min(DBL_MAX, DBL_MAX, DBL_MAX);
    FVector Max(-DBL_MAX, -DBL_MAX, -DBL_MAX);
    for (const TSharedPtr<FJsonValue>& PointValue : *Points)
    {
        FVector Point;
        if (!ReadVector(PointValue, Point))
        {
            return false;
        }
        Min.X = FMath::Min(Min.X, Point.X);
        Min.Y = FMath::Min(Min.Y, Point.Y);
        Max.X = FMath::Max(Max.X, Point.X);
        Max.Y = FMath::Max(Max.Y, Point.Y);
    }
    OutCenter = FVector((Min.X + Max.X) * 0.5, (Min.Y + Max.Y) * 0.5, 0.0);
    OutSize = FVector(Max.X - Min.X, Max.Y - Min.Y, 2.0);
    return OutSize.X > 0.0 && OutSize.Y > 0.0;
}

void AddRichPaths(
    const TSharedPtr<FJsonObject>& Root,
    const TCHAR* Field,
    FTerraRealitySliceLayout& Layout,
    const FVector& Anchor
)
{
    const TArray<TSharedPtr<FJsonValue>>* Paths = GetArray(Root, Field);
    if (!Paths)
    {
        return;
    }

    for (int32 PathIndex = 0; PathIndex < Paths->Num(); ++PathIndex)
    {
        if (!(*Paths)[PathIndex].IsValid() || (*Paths)[PathIndex]->Type != EJson::Object)
        {
            continue;
        }
        const TSharedPtr<FJsonObject> Path = (*Paths)[PathIndex]->AsObject();
        const TArray<TSharedPtr<FJsonValue>>* Points = GetArray(Path, TEXT("points_cm"));
        if (!Path || !Points || Points->Num() < 2)
        {
            continue;
        }
        FString PathId = FString::Printf(TEXT("path_%d"), PathIndex);
        Path->TryGetStringField(TEXT("id"), PathId);
        const float Width = ReadFloat(Path, TEXT("width_cm"), 240.0F);
        for (int32 Segment = 0; Segment + 1 < Points->Num(); ++Segment)
        {
            FVector Start;
            FVector End;
            if (!ReadVector((*Points)[Segment], Start) || !ReadVector((*Points)[Segment + 1], End))
            {
                continue;
            }
            const FVector Delta = End - Start;
            const float Length = FVector2D(Delta.X, Delta.Y).Size();
            if (Length < 1.0F)
            {
                continue;
            }
            FVector Center = (Start + End) * 0.5;
            Center.Z = FMath::Max(Center.Z + 2.0, Anchor.Z + 2.0);
            AddElement(
                Layout,
                FString::Printf(TEXT("rich_%s_%d"), *PathId, Segment),
                ETerraRealitySliceElementKind::Road,
                Center,
                FVector(Length, Width, 8.0),
                FMath::RadiansToDegrees(FMath::Atan2(Delta.Y, Delta.X)),
                true
            );
        }
    }
}

bool ParseRichLayout(
    const TSharedPtr<FJsonObject>& Root,
    FTerraRealitySliceLayout& OutLayout,
    FString& OutError
)
{
    FString Schema;
    if (!Root->TryGetStringField(TEXT("schema"), Schema) || Schema != TEXT("terra.reality-slice-layout/v1"))
    {
        OutError = TEXT("Unsupported rich reality-slice schema.");
        return false;
    }

    const TSharedPtr<FJsonObject> Scope = GetObject(Root, TEXT("scope"));
    FVector Anchor;
    if (!Scope || !ReadVectorField(Scope, TEXT("anchor_cm"), Anchor))
    {
        OutError = TEXT("Rich layout requires scope.anchor_cm.");
        return false;
    }

    OutLayout.SchemaVersion = RuntimeSchemaVersion;
    Root->TryGetStringField(TEXT("slice_id"), OutLayout.LayoutId);
    Scope->TryGetStringField(TEXT("name"), OutLayout.Title);
    OutLayout.ExtentCm = FVector2D(
        ReadFloat(Scope, TEXT("width_m"), 200.0F) * 100.0F,
        ReadFloat(Scope, TEXT("height_m"), 200.0F) * 100.0F
    );
    OutLayout.PlayerStart.LocationCm = Anchor + FVector(450.0, 250.0, 120.0);
    OutLayout.PlayerStart.YawDeg = 90.0F;

    AddElement(
        OutLayout,
        TEXT("rich_ground"),
        ETerraRealitySliceElementKind::Ground,
        Anchor - FVector(0.0, 0.0, 20.0),
        FVector(OutLayout.ExtentCm.X, OutLayout.ExtentCm.Y, 40.0),
        0.0F,
        true
    );
    AddRichPaths(Root, TEXT("roads"), OutLayout, Anchor);
    AddRichPaths(Root, TEXT("service_paths"), OutLayout, Anchor);

    const TArray<TSharedPtr<FJsonValue>>* Buildings = GetArray(Root, TEXT("buildings"));
    if (!Buildings || Buildings->IsEmpty())
    {
        OutError = TEXT("Rich layout requires buildings.");
        return false;
    }

    for (int32 Index = 0; Index < Buildings->Num(); ++Index)
    {
        if (!(*Buildings)[Index].IsValid() || (*Buildings)[Index]->Type != EJson::Object)
        {
            continue;
        }
        const TSharedPtr<FJsonObject> Building = (*Buildings)[Index]->AsObject();
        FVector Base;
        FVector Size;
        if (!Building || !ReadVectorField(Building, TEXT("pos_cm"), Base)
            || !ReadVectorField(Building, TEXT("size_cm"), Size))
        {
            continue;
        }
        FString Id = FString::Printf(TEXT("building_%d"), Index);
        FString RichKind;
        FString Prototype;
        Building->TryGetStringField(TEXT("id"), Id);
        Building->TryGetStringField(TEXT("kind"), RichKind);
        Building->TryGetStringField(TEXT("prototype"), Prototype);
        const float Yaw = ReadFloat(Building, TEXT("yaw_deg"));

        ETerraRealitySliceElementKind BodyKind = ETerraRealitySliceElementKind::Building;
        if (RichKind == TEXT("wall_segment")) BodyKind = ETerraRealitySliceElementKind::Wall;
        else if (RichKind == TEXT("gatehouse")) BodyKind = ETerraRealitySliceElementKind::Gate;
        else if (RichKind == TEXT("market_pavilion")) BodyKind = ETerraRealitySliceElementKind::MarketStall;

        AddElement(OutLayout, Id + TEXT("_body"), BodyKind, Base + FVector(0.0, 0.0, Size.Z * 0.5), Size, Yaw, true);
        if (BodyKind != ETerraRealitySliceElementKind::Wall)
        {
            AddElement(
                OutLayout,
                Id + TEXT("_roof"),
                ETerraRealitySliceElementKind::Roof,
                Base + FVector(0.0, 0.0, Size.Z + 10.0),
                FVector(Size.X + 30.0, Size.Y + 30.0, 20.0),
                Yaw,
                false
            );
        }

        const TSharedPtr<FJsonObject> Frontage = GetObject(Building, TEXT("frontage"));
        FVector Entry;
        if (Frontage && ReadVectorField(Frontage, TEXT("entry_cm"), Entry))
        {
            AddElement(
                OutLayout,
                Id + TEXT("_door"),
                ETerraRealitySliceElementKind::Door,
                FVector(Entry.X, Entry.Y, Base.Z + 110.0),
                FVector(20.0, 100.0, 220.0),
                Yaw,
                false
            );

            if (BodyKind == ETerraRealitySliceElementKind::Building)
            {
                const float Radians = FMath::DegreesToRadians(Yaw);
                const FVector Tangent(-FMath::Sin(Radians), FMath::Cos(Radians), 0.0);
                for (int32 WindowIndex = 0; WindowIndex < 2; ++WindowIndex)
                {
                    const float Offset = Size.Y * (WindowIndex == 0 ? -0.27F : 0.27F);
                    AddElement(
                        OutLayout,
                        FString::Printf(TEXT("%s_window_%d"), *Id, WindowIndex),
                        ETerraRealitySliceElementKind::Window,
                        FVector(Entry.X, Entry.Y, Base.Z + 210.0) + Tangent * Offset,
                        FVector(16.0, 90.0, 100.0),
                        Yaw,
                        false
                    );
                }
            }

            if (Prototype.Contains(TEXT("shop")) || Prototype.Contains(TEXT("timber_shade")))
            {
                const float Radians = FMath::DegreesToRadians(Yaw);
                const FVector Normal(FMath::Cos(Radians), FMath::Sin(Radians), 0.0);
                AddElement(
                    OutLayout,
                    Id + TEXT("_awning"),
                    ETerraRealitySliceElementKind::Awning,
                    FVector(Entry.X, Entry.Y, Base.Z + 245.0) + Normal * 90.0,
                    FVector(180.0, Size.Y * 0.8, 18.0),
                    Yaw,
                    false
                );
            }
        }
    }

    const TArray<TSharedPtr<FJsonValue>>* Courtyards = GetArray(Root, TEXT("courtyards"));
    if (Courtyards)
    {
        for (int32 Index = 0; Index < Courtyards->Num(); ++Index)
        {
            if (!(*Courtyards)[Index].IsValid() || (*Courtyards)[Index]->Type != EJson::Object)
            {
                continue;
            }
            const TSharedPtr<FJsonObject> Courtyard = (*Courtyards)[Index]->AsObject();
            FVector Center;
            FVector Size;
            if (PolygonBounds(Courtyard, TEXT("polygon_cm"), Center, Size))
            {
                Center.Z = Anchor.Z + 1.0;
                AddElement(
                    OutLayout,
                    FString::Printf(TEXT("rich_courtyard_%d"), Index),
                    ETerraRealitySliceElementKind::Courtyard,
                    Center,
                    Size,
                    0.0F,
                    false
                );
            }
        }
    }

    const TArray<TSharedPtr<FJsonValue>>* PublicSpaces = GetArray(Root, TEXT("public_spaces"));
    if (PublicSpaces)
    {
        for (int32 SpaceIndex = 0; SpaceIndex < PublicSpaces->Num(); ++SpaceIndex)
        {
            if (!(*PublicSpaces)[SpaceIndex].IsValid() || (*PublicSpaces)[SpaceIndex]->Type != EJson::Object)
            {
                continue;
            }
            const TSharedPtr<FJsonObject> Space = (*PublicSpaces)[SpaceIndex]->AsObject();
            FVector Center;
            FVector Size;
            if (PolygonBounds(Space, TEXT("polygon_cm"), Center, Size))
            {
                Center.Z = Anchor.Z + 1.0;
                AddElement(
                    OutLayout,
                    FString::Printf(TEXT("rich_public_space_%d"), SpaceIndex),
                    ETerraRealitySliceElementKind::PublicSpace,
                    Center,
                    Size,
                    0.0F,
                    false
                );
            }
            const TArray<TSharedPtr<FJsonValue>>* Amenities = GetArray(Space, TEXT("amenities"));
            if (!Amenities)
            {
                continue;
            }
            for (int32 AmenityIndex = 0; AmenityIndex < Amenities->Num(); ++AmenityIndex)
            {
                if (!(*Amenities)[AmenityIndex].IsValid() || (*Amenities)[AmenityIndex]->Type != EJson::Object)
                {
                    continue;
                }
                const TSharedPtr<FJsonObject> Amenity = (*Amenities)[AmenityIndex]->AsObject();
                FString Kind;
                FVector Position;
                if (Amenity && Amenity->TryGetStringField(TEXT("kind"), Kind)
                    && Kind == TEXT("public_well") && ReadVectorField(Amenity, TEXT("pos_cm"), Position))
                {
                    AddElement(
                        OutLayout,
                        FString::Printf(TEXT("rich_well_%d_%d"), SpaceIndex, AmenityIndex),
                        ETerraRealitySliceElementKind::Well,
                        Position + FVector(0.0, 0.0, 75.0),
                        FVector(200.0, 200.0, 150.0),
                        0.0F,
                        true
                    );
                }
            }
        }
    }

    NormalizeXY(OutLayout, Anchor);
    return true;
}

FVector RotateLocalXY(const FVector& Local, const float YawDeg)
{
    const float Radians = FMath::DegreesToRadians(YawDeg);
    return FVector(
        Local.X * FMath::Cos(Radians) - Local.Y * FMath::Sin(Radians),
        Local.X * FMath::Sin(Radians) + Local.Y * FMath::Cos(Radians),
        Local.Z
    );
}

void AddFallbackBuilding(
    FTerraRealitySliceLayout& Layout,
    const FString& Id,
    const FVector& CenterXY,
    const FVector& Size,
    const float Yaw,
    const bool bAwning
)
{
    AddElement(Layout, Id + TEXT("_body"), ETerraRealitySliceElementKind::Building, FVector(CenterXY.X, CenterXY.Y, Size.Z * 0.5), Size, Yaw, true);
    AddElement(Layout, Id + TEXT("_roof"), ETerraRealitySliceElementKind::Roof, FVector(CenterXY.X, CenterXY.Y, Size.Z + 10.0), FVector(Size.X + 30.0, Size.Y + 30.0, 20.0), Yaw, false);

    const FVector Front = FVector(CenterXY.X, CenterXY.Y, 0.0) + RotateLocalXY(FVector(Size.X * 0.5 + 6.0, 0.0, 0.0), Yaw);
    AddElement(Layout, Id + TEXT("_door"), ETerraRealitySliceElementKind::Door, Front + FVector(0.0, 0.0, 110.0), FVector(20.0, 110.0, 220.0), Yaw, false);
    for (int32 Floor = 0; Floor < FMath::Clamp(FMath::RoundToInt(Size.Z / 320.0), 1, 3); ++Floor)
    {
        for (int32 Side = 0; Side < 2; ++Side)
        {
            const float Offset = Size.Y * (Side == 0 ? -0.27F : 0.27F);
            const FVector WindowOffset = RotateLocalXY(FVector(Size.X * 0.5 + 7.0, Offset, 0.0), Yaw);
            AddElement(
                Layout,
                FString::Printf(TEXT("%s_window_%d_%d"), *Id, Floor, Side),
                ETerraRealitySliceElementKind::Window,
                FVector(CenterXY.X, CenterXY.Y, 210.0 + Floor * 320.0) + WindowOffset,
                FVector(16.0, 100.0, 100.0),
                Yaw,
                false
            );
        }
    }
    if (bAwning)
    {
        const FVector AwningOffset = RotateLocalXY(FVector(Size.X * 0.5 + 90.0, 0.0, 0.0), Yaw);
        AddElement(Layout, Id + TEXT("_awning"), ETerraRealitySliceElementKind::Awning, FVector(CenterXY.X, CenterXY.Y, 255.0) + AwningOffset, FVector(180.0, Size.Y * 0.8, 18.0), Yaw, false);
    }
}
} // namespace TerraRealitySliceLayout

bool UTerraRealitySliceLayoutLibrary::LoadBestAvailableLayout(
    FTerraRealitySliceLayout& OutLayout,
    FString& OutDiagnostic
)
{
    TArray<FString> Candidates;
    FString ExplicitPath;
    if (FParse::Value(FCommandLine::Get(), TEXT("TerraRealitySliceLayout="), ExplicitPath) && !ExplicitPath.IsEmpty())
    {
        Candidates.Add(FPaths::ConvertRelativePathToFull(ExplicitPath));
    }
    Candidates.Add(GetGeneratedRuntimeLayoutPath());
    Candidates.Add(FPaths::Combine(FPaths::ProjectDir(), TEXT("Scripts/terra_data/generated/reality_slice_capital.json")));

    TArray<FString> Failures;
    for (const FString& Candidate : Candidates)
    {
        if (!FPaths::FileExists(Candidate))
        {
            Failures.Add(FString::Printf(TEXT("missing %s"), *Candidate));
            continue;
        }

        FString Error;
        FTerraRealitySliceLayout CandidateLayout;
        if (LoadLayoutFromJsonFile(Candidate, CandidateLayout, Error))
        {
            OutLayout = MoveTemp(CandidateLayout);
            OutDiagnostic = FString::Printf(
                TEXT("Loaded validated spatial prototype '%s' from %s (%d runtime elements)."),
                *OutLayout.LayoutId,
                *Candidate,
                OutLayout.Elements.Num()
            );
            return true;
        }
        Failures.Add(FString::Printf(TEXT("invalid %s: %s"), *Candidate, *Error));
    }

    OutLayout = MakeSafeFallbackLayout();
    OutLayout.bUsedFallback = true;
    OutLayout.SourcePath = TEXT("embedded-safe-fallback");
    FString FallbackError;
    if (!ValidateLayout(OutLayout, FallbackError))
    {
        OutDiagnostic = FString::Printf(TEXT("Embedded reality-slice fallback is invalid: %s"), *FallbackError);
        return false;
    }

    OutDiagnostic = FString::Printf(
        TEXT("No external layout passed validation; using deterministic spatial fallback. %s"),
        *FString::Join(Failures, TEXT(" | "))
    );
    return true;
}

bool UTerraRealitySliceLayoutLibrary::LoadLayoutFromJsonFile(
    const FString& JsonPath,
    FTerraRealitySliceLayout& OutLayout,
    FString& OutError
)
{
    FString Json;
    if (!FFileHelper::LoadFileToString(Json, *JsonPath))
    {
        OutError = FString::Printf(TEXT("Could not read %s"), *JsonPath);
        return false;
    }

    TSharedPtr<FJsonObject> Root;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root)
    {
        OutError = FString::Printf(TEXT("Invalid JSON in %s"), *JsonPath);
        return false;
    }

    FTerraRealitySliceLayout Parsed;
    if (Root->HasField(TEXT("schema_version")))
    {
        if (!TerraRealitySliceLayout::ParseRuntimeAdapter(Root, Parsed, OutError))
        {
            return false;
        }
    }
    else if (!TerraRealitySliceLayout::ParseRichLayout(Root, Parsed, OutError))
    {
        return false;
    }

    Parsed.SourcePath = FPaths::ConvertRelativePathToFull(JsonPath);
    TerraRealitySliceLayout::FlattenToEngineeringDatum(Parsed);
    FString SpawnDiagnostic;
    if (!ResolveSafePlayerStart(Parsed, SpawnDiagnostic))
    {
        OutError = FString::Printf(TEXT("Layout has no safe pedestrian PlayerStart: %s"), *SpawnDiagnostic);
        return false;
    }
    if (!ValidateLayout(Parsed, OutError))
    {
        return false;
    }
    OutLayout = MoveTemp(Parsed);
    return true;
}

bool UTerraRealitySliceLayoutLibrary::ValidateLayout(
    const FTerraRealitySliceLayout& Layout,
    FString& OutError
)
{
    if (Layout.SchemaVersion != TerraRealitySliceLayout::RuntimeSchemaVersion || Layout.LayoutId.IsEmpty())
    {
        OutError = TEXT("Layout requires schema version 1 and a non-empty id.");
        return false;
    }
    if (!FMath::IsFinite(Layout.ExtentCm.X) || !FMath::IsFinite(Layout.ExtentCm.Y)
        || Layout.ExtentCm.X < 15000.0 || Layout.ExtentCm.X > 25000.0
        || Layout.ExtentCm.Y < 15000.0 || Layout.ExtentCm.Y > 25000.0)
    {
        OutError = TEXT("Reality slice must be a bounded ward between 150 and 250 metres per side.");
        return false;
    }
    if (Layout.Elements.IsEmpty() || Layout.Elements.Num() > TerraRealitySliceLayout::MaxRuntimeElements)
    {
        OutError = TEXT("Layout has an invalid runtime element count.");
        return false;
    }
    if (!TerraRealitySliceLayout::IsFiniteVector(Layout.PlayerStart.LocationCm)
        || FMath::Abs(Layout.PlayerStart.LocationCm.X) > Layout.ExtentCm.X * 0.5
        || FMath::Abs(Layout.PlayerStart.LocationCm.Y) > Layout.ExtentCm.Y * 0.5)
    {
        OutError = TEXT("PlayerStart is non-finite or outside the normalized ward.");
        return false;
    }

    TSet<FString> Ids;
    TMap<ETerraRealitySliceElementKind, int32> Counts;
    for (const FTerraRealitySliceElement& Element : Layout.Elements)
    {
        if (Element.ElementId.IsEmpty() || Ids.Contains(Element.ElementId))
        {
            OutError = FString::Printf(TEXT("Duplicate or empty element id: %s"), *Element.ElementId);
            return false;
        }
        Ids.Add(Element.ElementId);
        if (!TerraRealitySliceLayout::IsFiniteVector(Element.LocationCm)
            || !TerraRealitySliceLayout::IsFiniteVector(Element.SizeCm)
            || Element.SizeCm.X <= 0.0 || Element.SizeCm.Y <= 0.0 || Element.SizeCm.Z <= 0.0
            || !FMath::IsFinite(Element.YawDeg) || !FMath::IsFinite(Element.PitchDeg))
        {
            OutError = FString::Printf(TEXT("Element %s has invalid transform/size."), *Element.ElementId);
            return false;
        }
        if (FMath::Abs(Element.LocationCm.X) > Layout.ExtentCm.X * 0.5 + Element.SizeCm.X * 0.5 + 500.0
            || FMath::Abs(Element.LocationCm.Y) > Layout.ExtentCm.Y * 0.5 + Element.SizeCm.Y * 0.5 + 500.0)
        {
            OutError = FString::Printf(TEXT("Element %s escapes the normalized ward."), *Element.ElementId);
            return false;
        }
        if (Element.bCollision && !FMath::IsNearlyZero(Element.PitchDeg, 0.01F))
        {
            OutError = FString::Printf(
                TEXT("Colliding element %s has pitch; the flat-datum capsule validator only accepts upright boxes."),
                *Element.ElementId
            );
            return false;
        }
        if (Element.Kind == ETerraRealitySliceElementKind::Gate)
        {
            TArray<FTerraRealitySliceElement> GatePiers;
            if (!TerraRealitySliceLayout::MakeGateCollisionPiers(Element, GatePiers, &OutError))
            {
                return false;
            }
        }
        Counts.FindOrAdd(Element.Kind) += 1;
    }

    const int32 BuiltMassCount = Counts.FindRef(ETerraRealitySliceElementKind::Building)
        + Counts.FindRef(ETerraRealitySliceElementKind::MarketStall)
        + Counts.FindRef(ETerraRealitySliceElementKind::Wall)
        + Counts.FindRef(ETerraRealitySliceElementKind::Gate);
    if (Counts.FindRef(ETerraRealitySliceElementKind::Ground) < 1
        || Counts.FindRef(ETerraRealitySliceElementKind::Road) < 4
        || BuiltMassCount < 20
        || Counts.FindRef(ETerraRealitySliceElementKind::Door) < 10
        || Counts.FindRef(ETerraRealitySliceElementKind::Window) < 20
        || Counts.FindRef(ETerraRealitySliceElementKind::Awning) < 2
        || Counts.FindRef(ETerraRealitySliceElementKind::MarketStall) < 4
        || Counts.FindRef(ETerraRealitySliceElementKind::Well) < 1
        || Counts.FindRef(ETerraRealitySliceElementKind::Wall) < 2
        || Counts.FindRef(ETerraRealitySliceElementKind::Gate) != 1)
    {
        OutError = TEXT("Layout lacks the required street/building/frontage/market/well/wall/gate spatial vocabulary.");
        return false;
    }

    FString SpawnReason;
    if (!IsPlayerStartClear(Layout, Layout.PlayerStart.LocationCm, SpawnReason))
    {
        OutError = FString::Printf(TEXT("PlayerStart is unsafe after normalization: %s"), *SpawnReason);
        return false;
    }

    OutError.Reset();
    return true;
}

FString UTerraRealitySliceLayoutLibrary::GetGeneratedRuntimeLayoutPath()
{
    return FPaths::ConvertRelativePathToFull(
        FPaths::Combine(
            FPaths::ProjectDir(),
            TEXT("Scripts/terra_data/generated/reality_slice_capital_runtime_v1.json")
        )
    );
}

bool UTerraRealitySliceLayoutLibrary::IsPlayerStartClear(
    const FTerraRealitySliceLayout& Layout,
    const FVector& CandidateLocationCm,
    FString& OutReason
)
{
    using namespace TerraRealitySliceLayout;

    if (!IsFiniteVector(CandidateLocationCm)
        || FMath::Abs(CandidateLocationCm.X) + PlayerCapsuleRadiusCm > Layout.ExtentCm.X * 0.5
        || FMath::Abs(CandidateLocationCm.Y) + PlayerCapsuleRadiusCm > Layout.ExtentCm.Y * 0.5)
    {
        OutReason = TEXT("capsule is outside the ward bounds");
        return false;
    }

    for (const FTerraRealitySliceElement& Element : Layout.Elements)
    {
        if (Element.Kind == ETerraRealitySliceElementKind::Road)
        {
            // Roads are navigable after spawn, but the first frame must begin on
            // pedestrian ground rather than intersecting a thin road slab edge.
            if (CircleOverlapsOrientedRect(CandidateLocationCm, PlayerCapsuleRadiusCm, Element))
            {
                OutReason = FString::Printf(TEXT("capsule overlaps road footprint %s"), *Element.ElementId);
                return false;
            }
            continue;
        }

        if (!Element.bCollision || Element.Kind == ETerraRealitySliceElementKind::Ground)
        {
            continue;
        }

        if (Element.Kind == ETerraRealitySliceElementKind::Gate)
        {
            TArray<FTerraRealitySliceElement> Piers;
            FString GateError;
            if (!MakeGateCollisionPiers(Element, Piers, &GateError))
            {
                OutReason = GateError;
                return false;
            }
            for (const FTerraRealitySliceElement& Pier : Piers)
            {
                if (CapsuleOverlapsBox(CandidateLocationCm, Pier))
                {
                    OutReason = FString::Printf(TEXT("capsule overlaps gate pier %s"), *Pier.ElementId);
                    return false;
                }
            }
            continue;
        }

        if (CapsuleOverlapsBox(CandidateLocationCm, Element))
        {
            OutReason = FString::Printf(TEXT("capsule overlaps colliding element %s"), *Element.ElementId);
            return false;
        }
    }

    OutReason.Reset();
    return true;
}

bool UTerraRealitySliceLayoutLibrary::ResolveSafePlayerStart(
    FTerraRealitySliceLayout& Layout,
    FString& OutDiagnostic
)
{
    using namespace TerraRealitySliceLayout;

    Layout.PlayerStart.LocationCm.Z = PlayerSpawnCenterZCm;
    FString Reason;
    if (IsPlayerStartClear(Layout, Layout.PlayerStart.LocationCm, Reason))
    {
        Layout.bPlayerStartRelocated = false;
        Layout.PlayerStartDiagnostic = TEXT("Source PlayerStart passed capsule and pedestrian-footprint validation.");
        OutDiagnostic = Layout.PlayerStartDiagnostic;
        return true;
    }

    const FVector Original = Layout.PlayerStart.LocationCm;
    constexpr double FineStepCm = 50.0;
    constexpr int32 FineRings = 60;
    for (int32 Ring = 1; Ring <= FineRings; ++Ring)
    {
        for (int32 XStep = -Ring; XStep <= Ring; ++XStep)
        {
            for (int32 YSign = -1; YSign <= 1; YSign += 2)
            {
                const FVector Candidate(
                    Original.X + XStep * FineStepCm,
                    Original.Y + YSign * Ring * FineStepCm,
                    PlayerSpawnCenterZCm
                );
                if (IsPlayerStartClear(Layout, Candidate, Reason))
                {
                    Layout.PlayerStart.LocationCm = Candidate;
                    Layout.bPlayerStartRelocated = true;
                    Layout.PlayerStartDiagnostic = FString::Printf(
                        TEXT("Unsafe source PlayerStart (%.0f, %.0f) relocated %.0f cm to pedestrian ground (%.0f, %.0f)."),
                        Original.X,
                        Original.Y,
                        FVector2D::Distance(FVector2D(Original), FVector2D(Candidate)),
                        Candidate.X,
                        Candidate.Y
                    );
                    OutDiagnostic = Layout.PlayerStartDiagnostic;
                    return true;
                }
            }
        }
        for (int32 YStep = -Ring + 1; YStep < Ring; ++YStep)
        {
            for (int32 XSign = -1; XSign <= 1; XSign += 2)
            {
                const FVector Candidate(
                    Original.X + XSign * Ring * FineStepCm,
                    Original.Y + YStep * FineStepCm,
                    PlayerSpawnCenterZCm
                );
                if (IsPlayerStartClear(Layout, Candidate, Reason))
                {
                    Layout.PlayerStart.LocationCm = Candidate;
                    Layout.bPlayerStartRelocated = true;
                    Layout.PlayerStartDiagnostic = FString::Printf(
                        TEXT("Unsafe source PlayerStart (%.0f, %.0f) relocated %.0f cm to pedestrian ground (%.0f, %.0f)."),
                        Original.X,
                        Original.Y,
                        FVector2D::Distance(FVector2D(Original), FVector2D(Candidate)),
                        Candidate.X,
                        Candidate.Y
                    );
                    OutDiagnostic = Layout.PlayerStartDiagnostic;
                    return true;
                }
            }
        }
    }

    OutDiagnostic = FString::Printf(
        TEXT("No clear pedestrian candidate within %.0f m of source spawn; last rejection: %s"),
        FineRings * FineStepCm / 100.0,
        *Reason
    );
    Layout.PlayerStartDiagnostic = OutDiagnostic;
    return false;
}

FTerraRealitySliceLayout UTerraRealitySliceLayoutLibrary::MakeSafeFallbackLayout()
{
    using namespace TerraRealitySliceLayout;

    FTerraRealitySliceLayout Layout;
    Layout.SchemaVersion = RuntimeSchemaVersion;
    Layout.LayoutId = TEXT("terra-spatial-fallback-ward-v1");
    Layout.Title = TEXT("TERRA deterministic fallback ward");
    Layout.ExtentCm = FVector2D(20000.0, 20000.0);
    Layout.PlayerStart.LocationCm = FVector(450.0, 250.0, 120.0);
    Layout.PlayerStart.YawDeg = 90.0F;
    Layout.SourceAnchorCm = FVector::ZeroVector;

    AddElement(Layout, TEXT("fallback_ground"), ETerraRealitySliceElementKind::Ground, FVector(0.0, 0.0, -20.0), FVector(20000.0, 20000.0, 40.0), 0.0F, true);
    const struct FPathSpec { const TCHAR* Id; FVector Location; FVector Size; float Yaw; } Paths[] = {
        {TEXT("main_avenue"), FVector(0.0, 0.0, 4.0), FVector(20000.0, 800.0, 8.0), 90.0F},
        {TEXT("market_street"), FVector(0.0, 0.0, 5.0), FVector(20000.0, 500.0, 10.0), 0.0F},
        {TEXT("lane_west"), FVector(-6500.0, 0.0, 4.0), FVector(20000.0, 400.0, 8.0), 90.0F},
        {TEXT("lane_east"), FVector(6500.0, 0.0, 4.0), FVector(20000.0, 400.0, 8.0), 90.0F},
        {TEXT("cross_south"), FVector(0.0, -6000.0, 4.0), FVector(20000.0, 400.0, 8.0), 0.0F},
        {TEXT("cross_north"), FVector(0.0, 6000.0, 4.0), FVector(20000.0, 400.0, 8.0), 0.0F},
    };
    for (const FPathSpec& Path : Paths)
    {
        AddElement(Layout, FString(TEXT("fallback_")) + Path.Id, ETerraRealitySliceElementKind::Road, Path.Location, Path.Size, Path.Yaw, true);
    }

    const TArray<TPair<FVector2D, FVector2D>> Intervals = {
        {FVector2D(-9500.0, -6800.0), FVector2D(2.0, 0.0)},
        {FVector2D(-6200.0, -500.0), FVector2D(4.0, 0.0)},
        {FVector2D(500.0, 6200.0), FVector2D(4.0, 0.0)},
        {FVector2D(6800.0, 9500.0), FVector2D(2.0, 0.0)},
    };
    const float RowY[] = {-8200.0F, -4800.0F, -800.0F, 800.0F, 4800.0F, 8200.0F};
    int32 BuildingIndex = 0;
    for (int32 RowIndex = 0; RowIndex < UE_ARRAY_COUNT(RowY); ++RowIndex)
    {
        const float Yaw = RowIndex % 2 == 0 ? -90.0F : 90.0F;
        for (const TPair<FVector2D, FVector2D>& Interval : Intervals)
        {
            const int32 Count = FMath::RoundToInt(Interval.Value.X);
            const float Width = (Interval.Key.Y - Interval.Key.X) / Count;
            for (int32 Unit = 0; Unit < Count; ++Unit)
            {
                const float X = Interval.Key.X + Width * (Unit + 0.5F);
                if (FMath::Abs(RowY[RowIndex]) < 1600.0F && FMath::Abs(X) < 4000.0F)
                {
                    continue;
                }
                const float Height = (BuildingIndex % 5 == 0) ? 960.0F : 640.0F;
                AddFallbackBuilding(
                    Layout,
                    FString::Printf(TEXT("fallback_house_%03d"), BuildingIndex),
                    FVector(X, RowY[RowIndex], 0.0),
                    FVector(1200.0, Width - 20.0F, Height),
                    Yaw,
                    BuildingIndex % 4 == 0
                );
                ++BuildingIndex;
            }
        }
    }

    AddFallbackBuilding(Layout, TEXT("fallback_temple"), FVector(-1400.0, 2350.0, 0.0), FVector(1200.0, 1800.0, 640.0), -90.0F, false);
    AddFallbackBuilding(Layout, TEXT("fallback_admin"), FVector(1400.0, 2350.0, 0.0), FVector(1200.0, 1800.0, 640.0), -90.0F, false);

    AddElement(Layout, TEXT("fallback_square"), ETerraRealitySliceElementKind::PublicSpace, FVector(0.0, 0.0, 1.0), FVector(3600.0, 3000.0, 2.0), 0.0F, false);
    AddElement(Layout, TEXT("fallback_well"), ETerraRealitySliceElementKind::Well, FVector(-450.0, 0.0, 75.0), FVector(200.0, 200.0, 150.0), 0.0F, true);
    for (int32 Stall = 0; Stall < 8; ++Stall)
    {
        const float X = Stall < 4 ? -2400.0F : 2400.0F;
        const float Y = -1200.0F + (Stall % 4) * 800.0F;
        AddElement(Layout, FString::Printf(TEXT("fallback_stall_%d"), Stall), ETerraRealitySliceElementKind::MarketStall, FVector(X, Y, 145.0), FVector(500.0, 500.0, 290.0), Stall < 4 ? 0.0F : 180.0F, true);
        AddElement(Layout, FString::Printf(TEXT("fallback_stall_awning_%d"), Stall), ETerraRealitySliceElementKind::Awning, FVector(X + (Stall < 4 ? 300.0F : -300.0F), Y, 280.0), FVector(220.0, 460.0, 20.0), Stall < 4 ? 0.0F : 180.0F, false);
    }

    AddElement(Layout, TEXT("fallback_south_wall_west"), ETerraRealitySliceElementKind::Wall, FVector(-5350.0, -9850.0, 300.0), FVector(9300.0, 300.0, 600.0), 0.0F, true);
    AddElement(Layout, TEXT("fallback_south_wall_east"), ETerraRealitySliceElementKind::Wall, FVector(5350.0, -9850.0, 300.0), FVector(9300.0, 300.0, 600.0), 0.0F, true);
    AddElement(Layout, TEXT("fallback_south_gate"), ETerraRealitySliceElementKind::Gate, FVector(0.0, -9600.0, 320.0), FVector(800.0, 1400.0, 640.0), -90.0F, true);

    Layout.bUsedFallback = true;
    Layout.SourcePath = TEXT("embedded-safe-fallback");
    FString SpawnDiagnostic;
    ResolveSafePlayerStart(Layout, SpawnDiagnostic);
    return Layout;
}
