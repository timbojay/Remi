import SwiftUI

struct TimelineView: View {
    @State private var events: [TimelineEvent] = []
    @State private var isLoading = true
    private let apiClient = APIClient()

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading...")
            } else if events.isEmpty {
                ContentUnavailableView(
                    "No Timeline Events",
                    systemImage: "clock.arrow.circlepath",
                    description: Text("Events with dates will appear here as you share your story.")
                )
            } else {
                List(events) { event in
                    HStack(alignment: .top, spacing: 12) {
                        // Date column
                        VStack {
                            Text(event.displayDate)
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundStyle(.blue)
                                .frame(width: 70, alignment: .trailing)
                        }

                        // Timeline line
                        Circle()
                            .fill(significanceColor(event.significance ?? 3))
                            .frame(width: 10, height: 10)
                            .padding(.top, 4)

                        // Content
                        VStack(alignment: .leading, spacing: 4) {
                            Text(event.value)
                                .font(.body)
                            HStack(spacing: 6) {
                                Text(event.category.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.caption2)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(.blue.opacity(0.1))
                                    .clipShape(Capsule())
                                if let name = event.subjectName {
                                    Text(name)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .navigationTitle("Timeline")
        .task { await loadTimeline() }
        .refreshable { await loadTimeline() }
    }

    private func loadTimeline() async {
        isLoading = true
        events = await apiClient.getTimeline()
        isLoading = false
    }

    private func significanceColor(_ sig: Int) -> Color {
        switch sig {
        case 5: return .red
        case 4: return .orange
        case 3: return .blue
        case 2: return .gray
        default: return .secondary
        }
    }
}
