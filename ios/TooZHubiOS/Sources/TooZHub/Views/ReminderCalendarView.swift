import SwiftUI

struct ReminderCalendarView: View {
    let reminders: [Reminder]
    @Binding var selectedMonth: Date
    @Binding var selectedDate: Date?
    let onSelectDate: (Date) -> Void

    private let calendar = Calendar.current

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            toolbar
            weekdaysHeader
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 7), spacing: 6) {
                ForEach(calendarDays, id: \.self) { day in
                    if let day {
                        calendarCell(for: day)
                    } else {
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(Color.clear)
                            .frame(height: 68)
                    }
                }
            }
        }
        .padding(Theme.Spacing.sm)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                .fill(Color.white.opacity(0.05))
        )
    }

    private var toolbar: some View {
        HStack {
            Button {
                shiftMonth(by: -1)
            } label: {
                Image(systemName: "chevron.left")
            }
            .buttonStyle(InlineChipButtonStyle(isSelected: false))

            Spacer()

            Text(monthTitle)
                .font(Theme.Typography.captionStrong)
                .foregroundStyle(.white)

            Spacer()

            Button {
                shiftMonth(by: 1)
            } label: {
                Image(systemName: "chevron.right")
            }
            .buttonStyle(InlineChipButtonStyle(isSelected: false))
        }
    }

    private var weekdaysHeader: some View {
        HStack(spacing: 6) {
            ForEach(calendar.shortWeekdaySymbols, id: \.self) { day in
                Text(day)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.Colors.textSecondary)
                    .frame(maxWidth: .infinity)
            }
        }
    }

    private func calendarCell(for day: Date) -> some View {
        let dayReminders = remindersForDay(day)
        let isToday = calendar.isDateInToday(day)
        let isSelected = selectedDate.map { calendar.isDate($0, inSameDayAs: day) } ?? false
        let completedCount = dayReminders.filter { $0.isCompleted == true }.count
        let activeCount = dayReminders.count - completedCount

        return Button {
            selectedDate = day
            onSelectDate(day)
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(dayNumber(day))
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.white)
                    Spacer(minLength: 0)
                    if dayReminders.count > 0 {
                        Text("\(dayReminders.count)")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(Theme.Colors.textOnLight)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Theme.Colors.lightCard, in: Capsule())
                    }
                }

                Spacer(minLength: 0)

                if dayReminders.isEmpty {
                    Text("Tap pro novou")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(Theme.Colors.textSecondary.opacity(0.72))
                        .lineLimit(1)
                } else {
                    VStack(alignment: .leading, spacing: 4) {
                        if activeCount > 0 {
                            dotRow(color: Theme.Colors.warning, text: "\(activeCount)x aktivní")
                        }
                        if completedCount > 0 {
                            dotRow(color: Color.green, text: "\(completedCount)x hotovo")
                        }
                    }
                }
            }
            .padding(8)
            .frame(maxWidth: .infinity, minHeight: 74, alignment: .topLeading)
            .background(backgroundColor(isToday: isToday, isSelected: isSelected, hasCompleted: completedCount > 0))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(borderColor(isToday: isToday, isSelected: isSelected), lineWidth: isSelected ? 1.5 : 1)
            )
        }
        .buttonStyle(.plain)
    }

    private func dotRow(color: Color, text: String) -> some View {
        HStack(spacing: 5) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
            Text(text)
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(Theme.Colors.textSecondary)
                .lineLimit(1)
        }
    }

    private var calendarDays: [Date?] {
        guard
            let monthInterval = calendar.dateInterval(of: .month, for: selectedMonth),
            let firstWeekInterval = calendar.dateInterval(of: .weekOfMonth, for: monthInterval.start),
            let lastWeekInterval = calendar.dateInterval(
                of: .weekOfMonth,
                for: monthInterval.end.addingTimeInterval(-1)
            )
        else {
            return []
        }

        var days: [Date?] = []
        var current = firstWeekInterval.start
        while current < lastWeekInterval.end {
            if calendar.isDate(current, equalTo: selectedMonth, toGranularity: .month) {
                days.append(current)
            } else {
                days.append(nil)
            }
            current = calendar.date(byAdding: .day, value: 1, to: current) ?? current.addingTimeInterval(86_400)
        }
        return days
    }

    private var monthTitle: String {
        selectedMonth.formatted(.dateTime.month(.wide).year())
    }

    private func remindersForDay(_ day: Date) -> [Reminder] {
        reminders.filter { reminder in
            guard let dueDate = reminder.dueDate else { return false }
            return calendar.isDate(dueDate, inSameDayAs: day)
        }
    }

    private func dayNumber(_ date: Date) -> String {
        String(calendar.component(.day, from: date))
    }

    private func backgroundColor(isToday: Bool, isSelected: Bool, hasCompleted: Bool) -> some ShapeStyle {
        if isSelected {
            return Theme.Colors.primary.opacity(0.24)
        }
        if hasCompleted {
            return Color.green.opacity(0.12)
        }
        if isToday {
            return Theme.Colors.accent.opacity(0.18)
        }
        return Color.white.opacity(0.02)
    }

    private func borderColor(isToday: Bool, isSelected: Bool) -> Color {
        if isSelected {
            return Theme.Colors.primary
        }
        if isToday {
            return Theme.Colors.accent.opacity(0.8)
        }
        return Theme.Colors.hairline
    }

    private func shiftMonth(by offset: Int) {
        if let shifted = calendar.date(byAdding: .month, value: offset, to: selectedMonth) {
            selectedMonth = shifted
        }
    }
}
