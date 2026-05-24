import SwiftUI

struct MainTabView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var authManager: AuthManager

    @State private var userSelection: UserTab = .dashboard
    @State private var serviceSelection: ServiceTab = .clients
    private let tabBarReservedHeight: CGFloat = 124

    private var role: String {
        (authManager.user?.role ?? "user").lowercased()
    }

    private var isServiceRole: Bool {
        role == "service"
    }

    var body: some View {
        Group {
            if isServiceRole {
                serviceShell
            } else {
                userShell
            }
        }
        .animation(.easeInOut(duration: 0.2), value: isServiceRole)
    }

    private var userShell: some View {
        ZStack(alignment: .bottom) {
            userContent
            .safeAreaInset(edge: .bottom) {
                Color.clear.frame(height: tabBarReservedHeight)
            }

            HubFloatingTabBar(
                items: UserTab.allCases.map {
                    HubFloatingTabBar.Item(
                        id: $0.rawValue,
                        title: $0.title,
                        icon: $0.icon,
                        isCenter: $0 == .service
                    )
                },
                selectedId: userSelection.rawValue
            ) { selectedId in
                guard let selected = UserTab(rawValue: selectedId) else { return }
                withAnimation(.spring(response: 0.32, dampingFraction: 0.82)) {
                    userSelection = selected
                }
            }
        }
        .onChange(of: env.requestedUserTab) { _, value in
            guard let value, let tab = UserTab(rawValue: value) else { return }
            withAnimation(.spring(response: 0.32, dampingFraction: 0.82)) {
                userSelection = tab
            }
            env.requestedUserTab = nil
        }
    }

    private var serviceShell: some View {
        ZStack(alignment: .bottom) {
            serviceContent
            .safeAreaInset(edge: .bottom) {
                Color.clear.frame(height: tabBarReservedHeight)
            }

            HubFloatingTabBar(
                items: ServiceTab.allCases.map {
                    HubFloatingTabBar.Item(
                        id: $0.rawValue,
                        title: $0.title,
                        icon: $0.icon,
                        isCenter: $0 == .reminders
                    )
                },
                selectedId: serviceSelection.rawValue
            ) { selectedId in
                guard let selected = ServiceTab(rawValue: selectedId) else { return }
                withAnimation(.spring(response: 0.32, dampingFraction: 0.82)) {
                    serviceSelection = selected
                }
            }
        }
        .onChange(of: env.requestedServiceTab) { _, value in
            guard let value, let tab = ServiceTab(rawValue: value) else { return }
            withAnimation(.spring(response: 0.32, dampingFraction: 0.82)) {
                serviceSelection = tab
            }
            env.requestedServiceTab = nil
        }
    }

    @ViewBuilder
    private var userContent: some View {
        switch userSelection {
        case .dashboard:
            DashboardView()
        case .vehicles:
            VehiclesView()
        case .service:
            ServiceView()
        case .reservations:
            ReservationsView()
        case .account:
            AccountView()
        }
    }

    @ViewBuilder
    private var serviceContent: some View {
        switch serviceSelection {
        case .clients:
            ServiceClientsView()
        case .reservations:
            ReservationsView()
        case .reminders:
            ServiceRemindersView()
        case .addVehicle:
            ServiceAddVehicleView()
        case .account:
            AccountView()
        }
    }
}

private enum UserTab: String, CaseIterable {
    case dashboard
    case vehicles
    case service
    case reservations
    case account

    var title: String {
        switch self {
        case .dashboard:
            return "Dashboard"
        case .vehicles:
            return "Vozidla"
        case .service:
            return "Servisy"
        case .reservations:
            return "Rezervace"
        case .account:
            return "Profil"
        }
    }

    var icon: String {
        switch self {
        case .dashboard:
            return "house"
        case .vehicles:
            return "car.fill"
        case .service:
            return "square.grid.2x2"
        case .reservations:
            return "calendar"
        case .account:
            return "gearshape"
        }
    }
}

private enum ServiceTab: String, CaseIterable {
    case clients
    case reservations
    case reminders
    case addVehicle
    case account

    var title: String {
        switch self {
        case .clients:
            return "Klienti"
        case .reservations:
            return "Kalendář"
        case .reminders:
            return "Připomínky"
        case .addVehicle:
            return "Přidat"
        case .account:
            return "Profil"
        }
    }

    var icon: String {
        switch self {
        case .clients:
            return "person.3"
        case .reservations:
            return "calendar"
        case .reminders:
            return "clock.badge"
        case .addVehicle:
            return "plus.circle"
        case .account:
            return "gearshape"
        }
    }
}

private struct HubFloatingTabBar: View {
    struct Item: Identifiable {
        let id: String
        let title: String
        let icon: String
        let isCenter: Bool
    }

    let items: [Item]
    let selectedId: String
    let onSelect: (String) -> Void

    var body: some View {
        HStack(alignment: .bottom, spacing: 0) {
            ForEach(items) { item in
                if item.isCenter {
                    centerButton(item)
                } else {
                    sideButton(item)
                }
            }
        }
        .padding(.horizontal, Theme.Spacing.md)
        .padding(.top, 2)
        .padding(.bottom, 6)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Theme.Colors.background.opacity(0.82))
                .overlay(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .stroke(Theme.Colors.hairline, lineWidth: 1)
                )
                .shadow(color: Theme.Shadow.strong, radius: 12, y: 6)
        )
        .padding(.horizontal, Theme.Spacing.md)
        .padding(.bottom, 6)
    }

    private func sideButton(_ item: Item) -> some View {
        let selected = selectedId == item.id

        return Button {
            onSelect(item.id)
        } label: {
            VStack(spacing: 4) {
                Image(systemName: item.icon)
                    .font(.system(size: 18, weight: .medium))
                    .symbolVariant(selected ? .fill : .none)
                Text(item.title)
                    .font(.system(size: 10, weight: .medium))
            }
            .foregroundStyle(selected ? Theme.Colors.primary : .white.opacity(0.90))
            .frame(maxWidth: .infinity)
            .padding(.top, 6)
            .padding(.bottom, 2)
        }
        .buttonStyle(.plain)
    }

    private func centerButton(_ item: Item) -> some View {
        let selected = selectedId == item.id

        return Button {
            onSelect(item.id)
        } label: {
            ZStack {
                Circle()
                    .fill(selected ? Theme.Colors.primary : Theme.Colors.primary.opacity(0.92))
                    .frame(width: 54, height: 54)
                    .shadow(color: Theme.Colors.primary.opacity(0.42), radius: 8, y: 4)
                Image(systemName: item.icon)
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(Theme.Colors.textOnLight)
            }
            .offset(y: -7)
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
    }
}
