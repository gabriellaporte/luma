"""Build-time stand-in for OpenCV.

windows_capture imports cv2 at module level but only calls it to save images, which this app never does.
Bundling the stub instead of the real package keeps the executable ~110 MB smaller.
"""
