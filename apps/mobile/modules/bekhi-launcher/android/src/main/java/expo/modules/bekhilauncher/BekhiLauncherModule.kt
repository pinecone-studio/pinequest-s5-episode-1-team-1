package expo.modules.bekhilauncher

import android.content.Context
import android.content.Intent
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * Opens any app on the phone by its name: lists the apps the home screen shows, with the names
 * under their icons, and starts one the way tapping its icon does.
 */
class BekhiLauncherModule : Module() {
  private val context: Context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("BekhiLauncher")

    AsyncFunction("listApps") {
      val pm = context.packageManager
      val home = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
      @Suppress("DEPRECATION")
      val found = pm.queryIntentActivities(home, 0)
      found
        .filter { it.activityInfo.packageName != context.packageName }
        .distinctBy { it.activityInfo.packageName }
        .map { mapOf("label" to it.loadLabel(pm).toString(), "packageName" to it.activityInfo.packageName) }
    }

    // false when the app is not installed.
    AsyncFunction("openApp") { packageName: String ->
      val launch = context.packageManager.getLaunchIntentForPackage(packageName)
      if (launch != null) {
        val activity = appContext.currentActivity
        if (activity != null) {
          activity.startActivity(launch)
        } else {
          context.startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
      }
      launch != null
    }
  }
}
