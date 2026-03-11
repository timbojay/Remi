import SwiftUI

struct BiographyView: View {
    @State private var biography: String = ""
    @State private var isLoading = true
    @State private var isGenerating = false
    private let apiClient = APIClient()

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading biography...")
            } else if biography.isEmpty || biography == "No biographical information recorded yet." {
                ContentUnavailableView(
                    "No Biography Yet",
                    systemImage: "book",
                    description: Text("Start chatting to build your biography. Once enough facts are collected, a prose biography will be generated here.")
                )
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        // Render markdown-ish content
                        ForEach(paragraphs, id: \.self) { paragraph in
                            if paragraph.hasPrefix("# ") {
                                Text(String(paragraph.dropFirst(2)))
                                    .font(.title)
                                    .fontWeight(.bold)
                                    .padding(.top, 8)
                            } else if paragraph.hasPrefix("## ") {
                                Text(String(paragraph.dropFirst(3)))
                                    .font(.title2)
                                    .fontWeight(.semibold)
                                    .padding(.top, 12)
                            } else if paragraph.hasPrefix("### ") {
                                Text(String(paragraph.dropFirst(4)))
                                    .font(.title3)
                                    .fontWeight(.medium)
                                    .padding(.top, 8)
                            } else {
                                Text(paragraph)
                                    .font(.body)
                                    .lineSpacing(4)
                            }
                        }
                    }
                    .padding()
                    .frame(maxWidth: 700, alignment: .leading)
                }
            }
        }
        .navigationTitle("Biography")
        .toolbar {
            ToolbarItem {
                Button {
                    Task { await regenerate() }
                } label: {
                    if isGenerating {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Image(systemName: "arrow.clockwise")
                    }
                }
                .help("Regenerate biography")
                .disabled(isGenerating)
            }
        }
        .task { await loadBiography() }
    }

    private var paragraphs: [String] {
        biography
            .components(separatedBy: "\n\n")
            .flatMap { $0.components(separatedBy: "\n") }
            .filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    private func loadBiography() async {
        isLoading = true
        if let response = await apiClient.getBiography() {
            biography = response.biography
        }
        isLoading = false
    }

    private func regenerate() async {
        isGenerating = true
        if let response = await apiClient.getBiography() {
            biography = response.biography
        }
        isGenerating = false
    }
}
