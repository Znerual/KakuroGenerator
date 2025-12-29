package com.kakuro;

/**
 * Java wrapper for the native CSP Solver.
 * This class provides methods to generate and solve Kakuro puzzles.
 */
public class CSPSolver {
    private long nativeHandle;
    private KakuroBoard board;
    
    static {
        System.loadLibrary("kakuro_jni");
    }
    
    /**
     * Difficulty levels for puzzle generation.
     */
    public enum Difficulty {
        VERY_EASY("very_easy"),
        EASY("easy"),
        MEDIUM("medium"),
        HARD("hard");
        
        private final String value;
        
        Difficulty(String value) {
            this.value = value;
        }
        
        public String getValue() {
            return value;
        }
    }
    
    /**
     * Create a new solver for the given board.
     * @param board The Kakuro board to solve
     */
    public CSPSolver(KakuroBoard board) {
        this.board = board;
        nativeHandle = nativeCreate(board.getNativeHandle());
        if (nativeHandle == 0) {
            throw new RuntimeException("Failed to create native solver");
        }
    }
    
    /**
     * Generate a complete, unique Kakuro puzzle.
     * @param difficulty Difficulty level
     * @return true if successful, false otherwise
     */
    public boolean generatePuzzle(Difficulty difficulty) {
        checkHandle();
        return nativeGeneratePuzzle(nativeHandle, difficulty.getValue());
    }
    
    /**
     * Generate a medium difficulty puzzle.
     * @return true if successful, false otherwise
     */
    public boolean generatePuzzle() {
        return generatePuzzle(Difficulty.MEDIUM);
    }
    
    /**
     * Calculate clues based on the current board state.
     */
    public void calculateClues() {
        checkHandle();
        nativeCalculateClues(nativeHandle);
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
            throw new IllegalStateException("Native solver has been destroyed");
        }
    }
    
    // Native methods
    private native long nativeCreate(long boardHandle);
    private native void nativeDestroy(long handle);
    private native boolean nativeGeneratePuzzle(long handle, String difficulty);
    private native void nativeCalculateClues(long handle);
}