import SwiftUI

struct CoverageView: View {
    @State private var coverage: [CoverageItem] = []
    @State private var gaps: [CoverageItem] = []
    @State private var isLoading = true
    private let apiClient = APIClient()

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading...")
            } else if coverage.isEmpty && gaps.isEmpty {
                ContentUnavailableView(
                    "No Coverage Data",
                    systemImage: "chart.bar",
                    description: Text("Coverage data will appear as facts are recorded about different life areas.")
                )
            } else {
                List {
                    if !coverage.isEmpty {
                        Section("Explored Areas") {
                            ForEach(coverage) { item in
                                CoverageRow(item: item)
                            }
                        }
                    }

                    if !gaps.isEmpty {
                        Section("Unexplored Areas") {
                            ForEach(gaps) { item in
                                CoverageRow(item: item)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Coverage")
        .task { await loadCoverage() }
        .refreshable { await loadCoverage() }
    }

    private func loadCoverage() async {
        isLoading = true
        if let response = await apiClient.getCoverage() {
            coverage = response.coverage
            gaps = response.gaps
        }
        isLoading = false
    }
}

struct CoverageRow: View {
    let item: CoverageItem

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(item.displayCategory)
                    .font(.body)
                    .fontWeight(.medium)
                HStack(spacing: 8) {
                    Label("\(item.factCount) facts", systemImage: "doc.text")
                        .font(.caption)
                    if item.avgConfidence > 0 {
                        Label(String(format: "%.0f%%", item.avgConfidence * 100), systemImage: "checkmark.circle")
                            .font(.caption)
                    }
                }
                .foregroundStyle(.secondary)
            }
            Spacer()
            CoverageBadge(level: item.coverageLevel)
        }
        .padding(.vertical, 4)
    }
}

struct CoverageBadge: View {
    let level: String

    var color: Color {
        switch level {
        case "strong": return .green
        case "moderate": return .yellow
        case "sparse": return .orange
        default: return .red
        }
    }

    var body: some View {
        Text(level.capitalized)
            .font(.caption2)
            .fontWeight(.medium)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}
