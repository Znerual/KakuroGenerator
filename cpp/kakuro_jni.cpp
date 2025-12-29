#ifndef KAKURO_JNI_H
#define KAKURO_JNI_H

#include <jni.h>
#include "kakuro_cpp.h"
#include <memory>
#include <string>

extern "C" {

// Board management
JNIEXPORT jlong JNICALL
Java_com_kakuro_KakuroBoard_nativeCreate(JNIEnv* env, jobject obj, jint width, jint height);

JNIEXPORT void JNICALL
Java_com_kakuro_KakuroBoard_nativeDestroy(JNIEnv* env, jobject obj, jlong handle);

JNIEXPORT void JNICALL
Java_com_kakuro_KakuroBoard_nativeGenerateTopology(JNIEnv* env, jobject obj, jlong handle, 
                                                    jdouble density, jint maxSectorLength);

JNIEXPORT jstring JNICALL
Java_com_kakuro_KakuroBoard_nativeToJson(JNIEnv* env, jobject obj, jlong handle);

// Solver management
JNIEXPORT jlong JNICALL
Java_com_kakuro_CSPSolver_nativeCreate(JNIEnv* env, jobject obj, jlong boardHandle);

JNIEXPORT void JNICALL
Java_com_kakuro_CSPSolver_nativeDestroy(JNIEnv* env, jobject obj, jlong handle);

JNIEXPORT jboolean JNICALL
Java_com_kakuro_CSPSolver_nativeGeneratePuzzle(JNIEnv* env, jobject obj, jlong handle, 
                                                jstring difficulty);

JNIEXPORT void JNICALL
Java_com_kakuro_CSPSolver_nativeCalculateClues(JNIEnv* env, jobject obj, jlong handle);

} // extern "C"

#endif // KAKURO_JNI_H