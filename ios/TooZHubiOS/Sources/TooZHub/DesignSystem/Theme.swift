import SwiftUI

enum Theme {
    static let appName = "Správa vozidel"

    enum Colors {
        static let pageTop = Color(red: 0.08, green: 0.10, blue: 0.14)
        static let pageMid = Color(red: 0.13, green: 0.16, blue: 0.22)
        static let pageBottom = Color(red: 0.19, green: 0.23, blue: 0.31)

        static let background = Color(red: 0.11, green: 0.14, blue: 0.20)
        static let surface = Color(red: 0.18, green: 0.22, blue: 0.31)
        static let elevated = Color(red: 0.27, green: 0.32, blue: 0.44)
        static let inputSurface = Color(red: 0.31, green: 0.36, blue: 0.49)

        static let lightCard = Color(red: 0.98, green: 0.98, blue: 0.99)
        static let lightMuted = Color(red: 0.92, green: 0.93, blue: 0.96)

        static let primary = Color(red: 0.95, green: 0.56, blue: 0.22)
        static let primaryDark = Color(red: 0.73, green: 0.36, blue: 0.13)
        static let accent = Color(red: 0.30, green: 0.75, blue: 0.86)

        static let warning = Color(red: 0.97, green: 0.74, blue: 0.31)
        static let danger = Color(red: 0.89, green: 0.36, blue: 0.38)

        static let textPrimary = Color.white
        static let textSecondary = Color(red: 0.86, green: 0.89, blue: 0.95)
        static let textOnLight = Color(red: 0.16, green: 0.18, blue: 0.23)
        static let textOnLightSecondary = Color(red: 0.31, green: 0.36, blue: 0.46)

        static let hairline = Color.white.opacity(0.13)
        static let cardHairline = Color(red: 0.84, green: 0.87, blue: 0.93)

        static let successSoft = Color(red: 0.90, green: 0.97, blue: 0.93)
        static let warningSoft = Color(red: 1.00, green: 0.94, blue: 0.84)
        static let dangerSoft = Color(red: 1.00, green: 0.90, blue: 0.90)

        static let pageGradient = LinearGradient(
            colors: [pageTop, pageMid, pageBottom],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )

        static let premiumGradient = LinearGradient(
            colors: [
                Color(red: 0.28, green: 0.33, blue: 0.45),
                Color(red: 0.46, green: 0.33, blue: 0.24)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )

        static let aiGreenGradient = LinearGradient(
            colors: [
                Color(red: 0.19, green: 0.55, blue: 0.60),
                Color(red: 0.36, green: 0.73, blue: 0.76)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )

        static let aiPinkGradient = LinearGradient(
            colors: [
                Color(red: 0.67, green: 0.43, blue: 0.33),
                Color(red: 0.89, green: 0.56, blue: 0.38)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    enum Spacing {
        static let xxs: CGFloat = 4
        static let xs: CGFloat = 8
        static let sm: CGFloat = 12
        static let md: CGFloat = 16
        static let lg: CGFloat = 20
        static let xl: CGFloat = 24
        static let xxl: CGFloat = 32
    }

    enum Radius {
        static let sm: CGFloat = 12
        static let md: CGFloat = 16
        static let lg: CGFloat = 22
        static let xl: CGFloat = 28
        static let pill: CGFloat = 999
    }

    enum Shadow {
        static let soft = Color.black.opacity(0.12)
        static let medium = Color.black.opacity(0.20)
        static let strong = Color.black.opacity(0.32)
    }

    enum Typography {
        static let largeTitle = Font.system(size: 34, weight: .bold, design: .default)
        static let title = Font.system(size: 30, weight: .bold, design: .default)
        static let sectionTitle = Font.system(size: 26, weight: .bold, design: .default)
        static let cardTitle = Font.system(size: 22, weight: .semibold, design: .default)
        static let headline = Font.system(size: 19, weight: .semibold, design: .default)
        static let body = Font.system(size: 17, weight: .regular, design: .default)
        static let bodyStrong = Font.system(size: 17, weight: .semibold, design: .default)
        static let caption = Font.system(size: 14, weight: .regular, design: .default)
        static let captionStrong = Font.system(size: 14, weight: .semibold, design: .default)
        static let tiny = Font.system(size: 12, weight: .medium, design: .default)
    }
}

struct HubPageBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background {
                ZStack {
                    Theme.Colors.pageGradient
                    Circle()
                        .fill(Color.white.opacity(0.10))
                        .frame(width: 340, height: 340)
                        .blur(radius: 22)
                        .offset(x: -170, y: -320)
                    Circle()
                        .fill(Theme.Colors.primary.opacity(0.14))
                        .frame(width: 260, height: 260)
                        .blur(radius: 26)
                        .offset(x: 160, y: -260)
                }
                .ignoresSafeArea()
            }
    }
}

struct HubDarkCardModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(Theme.Spacing.md)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .fill(Theme.Colors.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .stroke(Theme.Colors.hairline, lineWidth: 1)
            )
            .shadow(color: Theme.Shadow.medium, radius: 12, y: 8)
    }
}

struct HubLightCardModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(Theme.Spacing.md)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.xl, style: .continuous)
                    .fill(Theme.Colors.lightCard)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.xl, style: .continuous)
                    .stroke(Theme.Colors.cardHairline.opacity(0.6), lineWidth: 1)
            )
            .shadow(color: Theme.Shadow.soft, radius: 10, y: 6)
    }
}

struct HubSectionContainerModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(Theme.Spacing.md)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .fill(Theme.Colors.surface.opacity(0.92))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .stroke(Theme.Colors.hairline, lineWidth: 1)
            )
    }
}

struct GlassBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .stroke(Color.white.opacity(0.18), lineWidth: 1)
            )
            .shadow(color: Theme.Shadow.medium, radius: 12, y: 8)
    }
}

extension View {
    func hubPageBackground() -> some View {
        modifier(HubPageBackground())
    }

    func hubDarkCard() -> some View {
        modifier(HubDarkCardModifier())
    }

    func hubLightCard() -> some View {
        modifier(HubLightCardModifier())
    }

    func hubSectionContainer() -> some View {
        modifier(HubSectionContainerModifier())
    }

    func glassStyle() -> some View {
        modifier(GlassBackground())
    }

    func appBackground() -> some View {
        hubPageBackground()
    }
}
