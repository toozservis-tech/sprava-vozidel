import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

struct ServerStatusBadge: View {
    let state: ServerStatusMonitor.State

    private var color: Color {
        switch state {
        case .online:
            return Theme.Colors.primary
        case .connecting:
            return Theme.Colors.warning
        case .offline:
            return Theme.Colors.danger
        }
    }

    private var label: String {
        switch state {
        case .online:
            return "Server online"
        case .connecting:
            return "Připojování"
        case .offline:
            return "Server offline"
        }
    }

    var body: some View {
        HStack(spacing: Theme.Spacing.xs) {
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
            Text(label)
                .font(Theme.Typography.tiny)
                .foregroundStyle(.white)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(.black.opacity(0.44), in: Capsule())
    }
}

struct BrandBadge: View {
    var body: some View {
        HStack(spacing: Theme.Spacing.sm) {
            Group {
                #if canImport(UIKit)
                if let logo = UIImage(named: "AppLogo") {
                    Image(uiImage: logo)
                        .resizable()
                        .scaledToFit()
                } else {
                    Image(systemName: "car.2.fill")
                        .resizable()
                        .scaledToFit()
                        .padding(8)
                        .foregroundStyle(.white)
                        .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                #else
                Image(systemName: "car.2.fill")
                    .resizable()
                    .scaledToFit()
                    .padding(8)
                    .foregroundStyle(.white)
                    .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                #endif
            }
            .frame(width: 38, height: 38)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

            VStack(alignment: .leading, spacing: 2) {
                Text(Theme.appName)
                    .font(Theme.Typography.headline)
                    .foregroundStyle(.white)
                Text("Digitální servisní přehled")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textSecondary)
            }
            Spacer()
        }
    }
}

struct SectionHeader: View {
    enum Tone {
        case dark
        case light
    }

    let title: String
    var subtitle: String?
    var trailing: AnyView?
    var tone: Tone = .dark

    private var titleColor: Color {
        tone == .light ? Theme.Colors.textOnLight : .white
    }

    private var subtitleColor: Color {
        tone == .light ? Theme.Colors.textOnLightSecondary : Theme.Colors.textSecondary
    }

    init(title: String, subtitle: String? = nil, trailing: AnyView? = nil, tone: Tone = .dark) {
        self.title = title
        self.subtitle = subtitle
        self.trailing = trailing
        self.tone = tone
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Theme.Typography.cardTitle)
                    .foregroundStyle(titleColor)
                if let subtitle {
                    Text(subtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(subtitleColor)
                }
            }
            Spacer()
            trailing
        }
    }
}

struct PillBadge: View {
    let title: String
    var style: Style = .neutral

    enum Style {
        case neutral
        case success
        case warning
        case danger

        var foreground: Color {
            switch self {
            case .neutral:
                return Theme.Colors.textOnLight
            case .success:
                return Theme.Colors.textOnLight
            case .warning:
                return Theme.Colors.textOnLight
            case .danger:
                return .white
            }
        }

        var background: Color {
            switch self {
            case .neutral:
                return Theme.Colors.lightMuted
            case .success:
                return Theme.Colors.successSoft
            case .warning:
                return Theme.Colors.warningSoft
            case .danger:
                return Theme.Colors.danger
            }
        }
    }

    var body: some View {
        Text(title)
            .font(Theme.Typography.tiny)
            .foregroundStyle(style.foreground)
            .padding(.horizontal, Theme.Spacing.sm)
            .padding(.vertical, 6)
            .background(style.background, in: Capsule())
    }
}

struct StatCard: View {
    let title: String
    let value: String
    let subtitle: String
    let icon: String

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            HStack {
                Image(systemName: icon)
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(Theme.Colors.primaryDark)
                    .frame(width: 34, height: 34)
                    .background(Theme.Colors.successSoft, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                Spacer()
            }

            Text(title)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textOnLightSecondary)

            Text(value)
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(Theme.Colors.textOnLight)
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            Text(subtitle)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textOnLightSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .hubLightCard()
    }
}

struct VehicleCard: View {
    let vehicle: Vehicle
    var mode: VehicleCardMode = .grid

    private var yearText: String {
        vehicle.year.map(String.init) ?? "-"
    }

    private var plateText: String {
        let plate = vehicle.plate?.trimmingCharacters(in: .whitespacesAndNewlines)
        return (plate?.isEmpty == false) ? plate! : "Bez SPZ"
    }

    private var stkText: String {
        vehicle.stkValidUntil?.formatted(date: .abbreviated, time: .omitted) ?? "Nezadáno"
    }

    private var mileageText: String {
        guard let value = vehicle.preferredMileageKm else { return "Nezadáno" }
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.numberStyle = .decimal
        formatter.groupingSeparator = " "
        let formatted = formatter.string(from: NSNumber(value: value)) ?? String(value)
        return "\(formatted) km"
    }

    var body: some View {
        Group {
            switch mode {
            case .grid:
                gridCard
            case .list:
                listCard
            case .compact:
                compactCard
            }
        }
        .contentShape(Rectangle())
    }

    private var vehicleVisual: some View {
        AuthenticatedVehiclePhotoView(vehicle: vehicle, height: 138, cornerRadius: 18) {
            VehiclePhotoPlaceholderView(vehicle: vehicle)
        }
    }

    private var gridCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            vehicleVisual

            HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(vehicle.displayName)
                        .font(Theme.Typography.headline)
                        .foregroundStyle(Theme.Colors.textOnLight)
                        .lineLimit(2)
                    Text(vehicle.engine?.isEmpty == false ? vehicle.engine! : "Bez specifikace motoru")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                        .lineLimit(2)
                }
                Spacer(minLength: Theme.Spacing.sm)
                PillBadge(title: plateText)
            }

            HStack(spacing: Theme.Spacing.sm) {
                VehicleInfoPill(icon: "calendar", label: "Rok", value: yearText)
                VehicleInfoPill(icon: "gauge.medium", label: "STK", value: stkText)
                VehicleInfoPill(icon: "speedometer", label: "Km", value: mileageText)
            }

            if let vin = vehicle.vin, !vin.isEmpty {
                Text("VIN: \(vin)")
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
        .hubLightCard()
    }

    private var listCard: some View {
        HStack(alignment: .center, spacing: Theme.Spacing.md) {
            AuthenticatedVehiclePhotoView(vehicle: vehicle, height: 84, cornerRadius: 16) {
                VehiclePhotoPlaceholderView(vehicle: vehicle, compact: true)
            }
            .frame(width: 112)

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: Theme.Spacing.xs) {
                    VehicleBrandBadge(vehicle: vehicle, compact: true)
                    Text(vehicle.displayName)
                        .font(Theme.Typography.bodyStrong)
                        .foregroundStyle(Theme.Colors.textOnLight)
                        .lineLimit(2)
                }

                Text(vehicle.engine?.isEmpty == false ? vehicle.engine! : "Bez specifikace motoru")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                    .lineLimit(1)

                HStack(spacing: Theme.Spacing.sm) {
                    smallMeta(icon: "number", value: plateText)
                    smallMeta(icon: "gauge.medium", value: stkText)
                    smallMeta(icon: "speedometer", value: mileageText)
                }
            }

            Spacer(minLength: 0)
        }
        .hubLightCard()
    }

    private var compactCard: some View {
        HStack(spacing: Theme.Spacing.sm) {
            VehicleBrandBadge(vehicle: vehicle, compact: true)

            VStack(alignment: .leading, spacing: 4) {
                Text(vehicle.displayName)
                    .font(Theme.Typography.captionStrong)
                    .foregroundStyle(Theme.Colors.textOnLight)
                    .lineLimit(1)
                Text("\(plateText) • \(mileageText)")
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 0)

            if vehicle.hasUserPhoto {
                Image(systemName: "photo.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.Colors.primary)
            }
        }
        .padding(.horizontal, Theme.Spacing.md)
        .padding(.vertical, Theme.Spacing.sm)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                .fill(Theme.Colors.lightCard)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                .stroke(Theme.Colors.cardHairline.opacity(0.6), lineWidth: 1)
        )
        .shadow(color: Theme.Shadow.soft, radius: 8, y: 4)
    }

    private func smallMeta(icon: String, value: String) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 10, weight: .semibold))
            Text(value)
                .font(.system(size: 11, weight: .medium))
                .lineLimit(1)
        }
        .foregroundStyle(Theme.Colors.textOnLightSecondary)
    }
}

private struct VehicleInfoPill: View {
    let icon: String
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .foregroundStyle(Theme.Colors.accent)
            VStack(alignment: .leading, spacing: 0) {
                Text(label)
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                Text(value)
                    .font(Theme.Typography.captionStrong)
                    .foregroundStyle(Theme.Colors.textOnLight)
            }
        }
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, Theme.Spacing.xs)
        .background(Theme.Colors.lightMuted, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }
}

struct TimelineRow: View {
    let title: String
    let subtitle: String
    let date: Date?
    let color: Color
    var lightStyle: Bool = false

    private var titleColor: Color {
        lightStyle ? Theme.Colors.textOnLight : Theme.Colors.textPrimary
    }

    private var subtitleColor: Color {
        lightStyle ? Theme.Colors.textOnLightSecondary : Theme.Colors.textSecondary
    }

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
            Circle()
                .fill(color)
                .frame(width: 10, height: 10)
                .padding(.top, 6)

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(Theme.Typography.bodyStrong)
                    .foregroundStyle(titleColor)
                Text(subtitle)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(subtitleColor)
                Text(date?.formatted(date: .abbreviated, time: .shortened) ?? "Bez data")
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(subtitleColor.opacity(0.92))
            }

            Spacer()
        }
    }
}

struct QuickActionTile: View {
    let icon: String
    let title: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: Theme.Spacing.sm) {
                Image(systemName: icon)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(tint)
                    .frame(width: 56, height: 56)
                    .background(tint.opacity(0.16), in: RoundedRectangle(cornerRadius: 16, style: .continuous))

                Text(title)
                    .font(Theme.Typography.captionStrong)
                    .foregroundStyle(Theme.Colors.textOnLight)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, Theme.Spacing.sm)
            .padding(.horizontal, Theme.Spacing.xs)
            .background(Theme.Colors.lightCard, in: RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

struct QuickActionCompactTile: View {
    let icon: String
    let title: String
    let subtitle: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(tint)
                    .frame(width: 34, height: 34)
                    .background(tint.opacity(0.16), in: RoundedRectangle(cornerRadius: 11, style: .continuous))

                Text(title)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.Colors.textOnLight)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)

                Text(subtitle)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .frame(maxWidth: .infinity, minHeight: 82)
            .padding(.vertical, 6)
            .padding(.horizontal, 4)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .fill(Theme.Colors.lightCard)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .stroke(Theme.Colors.cardHairline.opacity(0.8), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

struct EmptyStateView: View {
    let icon: String
    let title: String
    let subtitle: String
    var actionTitle: String?
    var action: (() -> Void)?

    var body: some View {
        VStack(spacing: Theme.Spacing.md) {
            Image(systemName: icon)
                .font(.system(size: 34, weight: .medium))
                .foregroundStyle(Theme.Colors.primary)
                .frame(width: 86, height: 86)
                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous))

            VStack(spacing: 4) {
                Text(title)
                    .font(Theme.Typography.headline)
                    .foregroundStyle(Theme.Colors.textPrimary)
                    .multilineTextAlignment(.center)

                Text(subtitle)
                    .font(Theme.Typography.body)
                    .foregroundStyle(Theme.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(PrimaryActionButtonStyle())
            }
        }
        .frame(maxWidth: .infinity)
        .padding(Theme.Spacing.lg)
        .hubDarkCard()
    }
}

struct ErrorStateView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: Theme.Spacing.sm) {
            Image(systemName: "exclamationmark.octagon.fill")
                .font(.system(size: 30, weight: .semibold))
                .foregroundStyle(Theme.Colors.danger)

            Text("Nepodařilo se načíst data")
                .font(Theme.Typography.headline)
                .foregroundStyle(.white)

            Text(message)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
                .multilineTextAlignment(.center)

            Button("Zkusit znovu", action: retry)
                .buttonStyle(PrimaryActionButtonStyle())
                .padding(.top, 4)
        }
        .padding(Theme.Spacing.lg)
        .hubDarkCard()
    }
}

struct InfoRowCard: View {
    let icon: String
    let title: String
    let subtitle: String?
    var trailing: AnyView? = nil

    var body: some View {
        HStack(spacing: Theme.Spacing.sm) {
            Image(systemName: icon)
                .font(.headline)
                .foregroundStyle(Theme.Colors.accent)
                .frame(width: 34, height: 34)
                .background(Theme.Colors.lightMuted, in: RoundedRectangle(cornerRadius: 10, style: .continuous))

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Theme.Typography.bodyStrong)
                    .foregroundStyle(Theme.Colors.textOnLight)
                if let subtitle {
                    Text(subtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                }
            }

            Spacer()
            trailing
        }
        .hubLightCard()
    }
}
