import cv2
import numpy as np
import os

def main():
    image_path = 'sample_image.jpg'
    output_path = 'sample_output.jpg'
    
    # Read the image
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not read image at {image_path}")
        return

    # Initialize ArUco dictionary (4x4, 1000 markers max)
    try:
        aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
    except AttributeError:
        aruco_dict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_1000)

    # Initialize parameters
    try:
        aruco_params = cv2.aruco.DetectorParameters()
        detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)
        corners, ids, rejected = detector.detectMarkers(img)
    except AttributeError:
        aruco_params = cv2.aruco.DetectorParameters_create()
        corners, ids, rejected = cv2.aruco.detectMarkers(img, aruco_dict, parameters=aruco_params)

    if ids is None or len(ids) < 4:
        print("Error: Could not detect all 4 markers.")
        if ids is not None:
            print(f"Detected IDs: {ids.flatten()}")
            
        # Draw whatever was detected for debugging
        debug_img = img.copy()
        if ids is not None:
            cv2.aruco.drawDetectedMarkers(debug_img, corners, ids)
        cv2.imwrite('debug_markers.jpg', debug_img)
        print("Saved debug_markers.jpg to see what went wrong.")
        return

    print(f"Detected marker IDs: {ids.flatten()}")

    # Extract centers of each marker
    # Format of corners: (N, 1, 4, 2)
    marker_centers = {}
    for i, marker_id in enumerate(ids.flatten()):
        # corners[i][0] is an array of 4 points: [top-left, top-right, bottom-right, bottom-left]
        c = corners[i][0]
        center = np.mean(c, axis=0)
        marker_centers[marker_id] = center

    # We expect IDs 0, 1, 2, 3
    expected_ids = [0, 1, 2, 3]
    for req_id in expected_ids:
        if req_id not in marker_centers:
            print(f"Error: Marker ID {req_id} not found!")
            return

    # Define source points (the centers of the detected markers)
    # Based on Simulation.py: 0: TL, 1: TR, 2: BL, 3: BR
    # Perspective transform order: Top-Left, Top-Right, Bottom-Right, Bottom-Left
    src_pts = np.array([
        marker_centers[0], # Top-Left
        marker_centers[1], # Top-Right
        marker_centers[3], # Bottom-Right
        marker_centers[2]  # Bottom-Left
    ], dtype="float32")

    # Define destination dimensions (e.g. 1280x720)
    width, height = 1280, 720
    
    # We map the centers of the markers to these corners. 
    # This gives a nice flat top-down view bounded by the markers.
    dst_pts = np.array([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1]
    ], dtype="float32")

    # Calculate perspective transform matrix
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)

    # Warp the image
    warped = cv2.warpPerspective(img, M, (width, height))

    # Save the output
    cv2.imwrite(output_path, warped)
    print(f"Success! Warped image saved to {output_path}")
    
    # Draw the detected markers and the bounding polygon on the original image for debugging
    debug_img = img.copy()
    cv2.aruco.drawDetectedMarkers(debug_img, corners, ids)
    
    # Draw lines connecting the centers
    pts = src_pts.astype(int).reshape((-1, 1, 2))
    cv2.polylines(debug_img, [pts], isClosed=True, color=(0, 255, 0), thickness=3)
    
    cv2.imwrite('debug_markers.jpg', debug_img)
    print("Debug image with markers and warp boundary saved to debug_markers.jpg")

if __name__ == "__main__":
    main()
