import SwiftUI

@main
struct BiographerApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                #if os(macOS)
                .frame(minWidth: 700, minHeight: 500)
                #endif
        }
        #if os(macOS)
        .defaultSize(width: 950, height: 800)
        #endif
    }
}
