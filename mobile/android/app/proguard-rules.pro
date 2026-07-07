# Flutter Wrapper
-keep class io.flutter.app.** { *; }
-keep class io.flutter.plugin.**  { *; }
-keep class io.flutter.util.**  { *; }
-keep class io.flutter.view.**  { *; }
-keep class io.flutter.**  { *; }
-keep class io.flutter.plugins.**  { *; }

# TensorFlow Lite
-keep class org.tensorflow.lite.** { *; }
-dontwarn org.tensorflow.lite.**
-dontwarn org.tensorflow.lite.gpu.**

# OpenCV (se necessario in futuro)
-keep class org.opencv.** { *; }
-dontwarn org.opencv.**

# Ignora le classi mancanti di Play Core Tasks (causate dalla migrazione di Google)
-dontwarn com.google.android.play.core.tasks.**

# Sceneform / AR Flutter Plugin
-dontwarn com.google.ar.sceneform.animation.AnimationEngine
-dontwarn com.google.ar.sceneform.animation.AnimationLibraryLoader
-dontwarn com.google.ar.sceneform.assets.Loader
-dontwarn com.google.ar.sceneform.assets.ModelData
-dontwarn com.google.devtools.build.android.desugar.runtime.ThrowableExtension

-keep class com.google.ar.sceneform.** { *; }
-keep class com.google.ar.core.** { *; }
-dontwarn com.google.ar.sceneform.**
-dontwarn com.google.ar.core.**