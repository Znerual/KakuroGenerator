package com.kakuro;

/**
 * Java wrapper for the native Kakuro board.
 * This class manages the lifecycle of the native C++ board.
 */
public class KakuroBoard {
    private long nativeHandle;
    
    static {
        System.loadLibrary("kakuro_jni");
    }
    
    /**
     * Create a new Kakuro board.
     * @param width Board width
     * @param height Board height
     */
    public KakuroBoard(int width, int height) {
        nativeHandle = nativeCreate(width, height);
        if (nativeHandle == 0) {
            throw new RuntimeException("Failed to create native board");
        }
    }
    
    /**
     * Generate the board topology.
     * @param density Density of white cells (0.0 to 1.0)
     * @param maxSectorLength Maximum length of a sector
     */
    public void generateTopology(double density, int maxSectorLength) {
        checkHandle();
        nativeGenerateTopology(nativeHandle, density, maxSectorLength);
    }
    
    /**
     * Generate the board topology with default parameters.
     */
    public void generateTopology() {
        generateTopology(0.60, 9);
    }
    
    /**
     * Export the board to JSON format.
     * @return JSON string representing the board
     */
    public String toJson() {
        checkHandle();
        return nativeToJson(nativeHandle);
    }
    
    /**
     * Get the native handle (for internal use).
     * @return Native handle
     */
    long getNativeHandle() {
        return nativeHandle;
    }
    
    /**
     * Clean up native resources.
     */
    public void destroy() {
        if (nativeHandle != 0) {
            nativeDestroy(nativeHandle);
            nativeHandle = 0;
        }
    }
    
    @Override
    protected void finalize() throws Throwable {
        try {
            destroy();
        } finally {
            super.finalize();
        }
    }
    
    private void checkHandle() {
        if (nativeHandle == 0) {
            throw new IllegalStateException("Native board has been destroyed");
        }
    }
    
    // Native methods
    private native long nativeCreate(int width, int height);
    private native void nativeDestroy(long handle);
    private native void nativeGenerateTopology(long handle, double density, int maxSectorLength);
    private native String nativeToJson(long handle);
}