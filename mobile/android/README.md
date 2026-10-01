# Health Twin — Android app

Reads Android **Health Connect** (heart rate, steps, SpO₂, respiratory rate, body temperature, sleep) and syncs it to the twin server on your computer. Full guide: [../../docs/mobile.md](../../docs/mobile.md).

- **Build:** open this folder in Android Studio and press Run, or `./gradlew assembleDebug` (JDK 17). The APK is written to `app/build/outputs/apk/debug/app-debug.apk`. GitHub Actions builds it on every push (artifact `health-twin-apk`).
- **Code:** `MainActivity.kt` (pairing, permissions, sync loop, UI) · `HealthReader.kt` (paged Health Connect reads, per-minute averaging) · `TwinApi.kt` (HTTP) · `Prefs.kt` · `PermissionsRationaleActivity.kt` (privacy screen Health Connect links to).
- **Requirements:** Android 8.0+ (API 26). Health Connect is built into Android 14+; on older versions, install it from the Play Store.
