import time
from picamera2 import Picamera2
import cv2
import numpy as np

class Camera:
    def __init__(self):
        self.cam0 = Picamera2(0)
        config = self.cam0.create_preview_configuration(main={"size": (1920, 1080), "format": "RGB888"})
        self.cam0.configure(config)
        self.cam1 = Picamera2(1)
        self.cam0.start()
        self.cam1.start()

        self.cam0.set_controls({"AwbMode": 0, "ColourGains": (0.5, 1.0)})

    def capture_image(self, filename, camera0=True, camera1=True):
        # Allow the camera to warm up
        print("Warming up the camera...")
        print("3")
        time.sleep(1)
        print("2")
        time.sleep(1)
        print("1")
        time.sleep(1)
        print("Capturing image...")
        # Capture the image and save it to images/filename.jpg
        if(camera0):
            self.cam0.capture_file("images/{}_cam0.jpg".format(filename))
        if(camera1):
            self.cam1.capture_file("images/{}_cam1.jpg".format(filename))
        self.cam0.stop()
        self.cam1.stop()
        print("Image captured and saved as {}_cam0.jpg and {}_cam1.jpg".format(filename, filename))

    def create_NDVI(self, cam=0):
        # Single-camera NDVI
        if cam == 0:
            img = cv2.imread("images/test_image_cam0.jpg")
        elif cam == 1:
            img = cv2.imread("images/test_image_cam1.jpg")
        else:
            print("Invalid camera selection. Choose 0 or 1.")
            return
        
        img_float = img.astype(np.float32)

        # In a Blue-Filtered NoIR Camera:
        # Channel 0 (Blue) = Visible Blue + Infrared
        # Channel 1 (Green) = Mostly Infrared (Green is blocked by gel)
        # Channel 2 (Red)   = Pure Infrared (Red is blocked by gel)

        # Red channel is NIR source
        nir = img_float[:, :, 2]
        # Blue channel is visible light source
        vis = img_float[:, :, 0]

        avg_nir = np.mean(nir)
        avg_vis = np.mean(vis)

        if avg_nir == 0: avg_nir = 1
        calibration_factor = avg_vis / avg_nir
        nir_calibrated = nir * calibration_factor

        nir = nir * 1.3

        # Calculate NDVI values
        numerator = nir_calibrated - vis
        denominator = nir_calibrated + vis
        denominator[denominator == 0] = 0.01  # Prevent division by zero
        ndvi = numerator / denominator

        vmin, vmax = np.percentile(ndvi, (2, 98))

        ndvi_stretched = (ndvi - vmin) / (vmax - vmin) * 255
        ndvi_stretched = np.clip(ndvi_stretched, 0, 255).astype(np.uint8)

        ndvi_scaled = ((ndvi + 1) / 2) * 255
        ndvi_uint8 = ndvi_scaled.astype(np.uint8)

        heatmap = cv2.applyColorMap(ndvi_stretched, cv2.COLORMAP_JET)

        cv2.imwrite("ndvi_image_cam{}.jpg".format(cam), heatmap)
        print("NDVI image saved as ndvi_image_cam{}.jpg".format(cam))


    def create_NDVI_two_cam(self):
        # In this method, implement NDVI image creation logic
        # create image objects to pass into _align_images
        img1 = cv2.imread("images/test_image_cam0.jpg")
        img2 = cv2.imread("images/test_image_cam1.jpg")
        self._align_images(img1, img2)
    
    def _align_images(self, img1, img2):
        orb = cv2.ORB_create(5000)
        keypoints1, descriptors1 = orb.detectAndCompute(img1, None)
        keypoints2, descriptors2 = orb.detectAndCompute(img2, None)

        matcher = cv2.DescriptorMatcher_create(cv2.DESCRIPTOR_MATCHER_BRUTEFORCE_HAMMING)
        matches = matcher.match(descriptors1, descriptors2, None)
        print("Total matches found: ", len(matches))

        matches = sorted(matches, key=lambda x: x.distance)
        keep_amount = int(len(matches) * 0.15)
        matches = matches[:keep_amount]

        min_matches = 200
        print("Matches after filtering: ", len(matches))
        if len(matches) < min_matches:
            print("Not enough matches found - %d/%d" % (len(matches), 4))
            return None

        points_ref = np.zeros((len(matches), 2), dtype=np.float32)
        points_align = np.zeros((len(matches), 2), dtype=np.float32)

        for i, match in enumerate(matches):
            points_ref[i, :] = keypoints1[match.queryIdx].pt
            points_align[i, :] = keypoints2[match.trainIdx].pt

        h, mask = cv2.findHomography(points_align, points_ref, cv2.RANSAC)
        print("Homography matrix: \n", h)

        height, width, channels = img1.shape
        aligned_img = cv2.warpPerspective(img2, h, (width, height))

        # save the aligned image for verification
        cv2.imwrite("aligned_image.jpg", aligned_img)
        print("Aligned image saved as aligned_image.jpg")

if __name__ == "__main__":
    camera = Camera()
    camera.capture_image("test_image", camera0=True, camera1=True)
    camera.create_NDVI(cam=0)