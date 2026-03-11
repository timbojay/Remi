import SwiftUI

struct FactsView: View {
    @State private var facts: [Fact] = []
    @State private var isLoading = true
    @State private var selectedCategory: String? = nil
    private let apiClient = APIClient()

    private var categories: [String] {
        Array(Set(facts.map { $0.category })).sorted()
    }

    private var filteredFacts: [Fact] {
        if let cat = selectedCategory {
            return facts.filter { $0.category == cat }
        }
        return facts
    }

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading...")
            } else if facts.isEmpty {
                ContentUnavailableView(
                    "No Facts Yet",
                    systemImage: "doc.text",
                    description: Text("Biographical facts will appear here as you share your story.")
                )
            } else {
                VStack(spacing: 0) {
                    // Category filter
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            FilterChip(label: "All", isSelected: selectedCategory == nil) {
                                selectedCategory = nil
                            }
                            ForEach(categories, id: \.self) { cat in
                                FilterChip(
                                    label: cat.replacingOccurrences(of: "_", with: " ").capitalized,
                                    isSelected: selectedCategory == cat
                                ) {
                                    selectedCategory = cat
                                }
                            }
                        }
                        .padding(.horizontal)
                        .padding(.vertical, 8)
                    }

                    Divider()

                    List(filteredFacts) { fact in
                        HStack(spacing: 12) {
                            Image(systemName: fact.categoryIcon)
                                .foregroundStyle(.blue)
                                .frame(width: 20)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(fact.value)
                                    .font(.body)
                                HStack(spacing: 8) {
                                    Text(fact.displayCategory)
                                        .font(.caption2)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(.blue.opacity(0.1))
                                        .clipShape(Capsule())
                                    if let sig = fact.significance {
                                        HStack(spacing: 1) {
                                            ForEach(0..<sig, id: \.self) { _ in
                                                Image(systemName: "star.fill")
                                                    .font(.system(size: 8))
                                            }
                                        }
                                        .foregroundStyle(.orange)
                                    }
                                }
                            }
                            Spacer()
                            if fact.isVerified == 1 {
                                Image(systemName: "checkmark.seal.fill")
                                    .foregroundStyle(.green)
                                    .font(.caption)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                }
            }
        }
        .navigationTitle("Facts (\(filteredFacts.count))")
        .task { await loadFacts() }
        .refreshable { await loadFacts() }
    }

    private func loadFacts() async {
        isLoading = true
        facts = await apiClient.getFacts()
        isLoading = false
    }
}

struct FilterChip: View {
    let label: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.caption)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(isSelected ? Color.accentColor : Color.secondary.opacity(0.15))
                .foregroundStyle(isSelected ? .white : .primary)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}
