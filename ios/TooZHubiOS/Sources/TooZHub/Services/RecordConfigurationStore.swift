import Foundation

@MainActor
final class RecordConfigurationStore: ObservableObject {
    @Published private(set) var customCategories: [ServiceCategoryOption] = []
    @Published private(set) var customTemplates: [ServiceRecordTemplate] = []

    private let customTemplatesKey = "service_record_custom_templates_v1"
    private let customCategoriesKey = "service_record_custom_categories_v1"

    init() {
        load()
    }

    var categoryOptions: [ServiceCategoryOption] {
        ServiceCategoryOption.merged(with: customCategories)
    }

    var allTemplates: [ServiceRecordTemplate] {
        ServiceRecordTemplate.presets + customTemplates
    }

    func addCategory(label: String, icon: String = "🧩") {
        let trimmed = label.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        let normalizedId = slug(trimmed)
        guard !normalizedId.isEmpty else { return }
        guard !categoryOptions.contains(where: { $0.id == normalizedId }) else { return }

        customCategories.insert(
            ServiceCategoryOption(id: normalizedId, label: trimmed, icon: icon),
            at: 0
        )
        persistCategories()
    }

    func deleteCategory(id: String) {
        customCategories.removeAll { $0.id == id }
        persistCategories()
    }

    func saveTemplate(_ template: ServiceRecordTemplate) {
        customTemplates.removeAll { $0.id == template.id }
        customTemplates.insert(template, at: 0)
        persistTemplates()
    }

    func deleteTemplate(_ template: ServiceRecordTemplate) {
        customTemplates.removeAll { $0.id == template.id }
        persistTemplates()
    }

    private func load() {
        customCategories = loadValue(forKey: customCategoriesKey) ?? []
        customTemplates = loadValue(forKey: customTemplatesKey) ?? []
    }

    private func loadValue<T: Decodable>(forKey key: String) -> T? {
        guard let data = UserDefaults.standard.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    private func persistCategories() {
        persist(customCategories, forKey: customCategoriesKey)
    }

    private func persistTemplates() {
        persist(customTemplates, forKey: customTemplatesKey)
    }

    private func persist<T: Encodable>(_ value: T, forKey key: String) {
        guard let data = try? JSONEncoder().encode(value) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    private func slug(_ raw: String) -> String {
        let mutable = NSMutableString(string: raw) as CFMutableString
        CFStringTransform(mutable, nil, kCFStringTransformStripDiacritics, false)
        let normalized = (mutable as String)
            .uppercased()
            .replacingOccurrences(of: "[^A-Z0-9]+", with: "_", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
        return normalized
    }
}
