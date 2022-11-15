import os
import logging
from tempfile import TemporaryFile

import cv2
from PIL import Image

import tator
import inference


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Read environment variables that are provided from TATOR
# Environmental variables are fed in via YAML file
host = os.getenv('HOST') # URL https://cloud.tator.io/ (check slashes)
token = os.getenv('TOKEN') # Obtain from TATOR
project_id = int(os.getenv('PROJECT_ID')) # Project ID from URL of project (number after URL, 123 for example)
media_ids = [int(id_) for id_ in os.getenv('MEDIA_IDS').split(',')] # These are the files, media info, right-hand side, ID field there
frames_per_inference = int(os.getenv('FRAMES_PER_INFERENCE', 30)) # modify if needed 

# Set up the TATOR API.
api = tator.get_api(host, token)

# Iterate through each video.
for media_id in media_ids:

    # Download video.
    media = api.get_media(media_id)
    logger.info(f"Downloading {media.name}...")
    out_path = f"/tmp/{media.name}"
    for progress in tator.util.download_media(api, media, out_path):
        logger.info(f"Download progress: {progress}%")

    # Do inference on each video.
    logger.info(f"Doing inference on {media.name}...")
    localizations = []
    vid = cv2.VideoCapture(out_path)
    frame_number = 0

    # Read *every* frame from the video, break when at the end.
    while True:
        ret, frame = vid.read()
        if not ret:
            break

        # Create a temporary file, access the image data, save data to file.
        framefile = TemporaryFile(suffix='.jpg')
        im = Image.fromarray(frame)
        im.save(framefile)

        # For every N frames, make a prediction; append prediction results
        # to a list, increase the frame count.
        if frame_number % frames_per_inference == 0:
            
            # Predictions contains a list; each index contains a dict (spec)
            # specifying the following:
            # TATOR expects normalized pixel coordinates, important for multiscale, normalize against the base
            # x - left-most
            # y - upper-most
            # width - width of bbox (x2 - x)
            # height - height of bbox (y2 - y)
            # class_category - string of top prediction, change this to be species name
            # confidence - float of confidence scores [0-1]
            # Any additional user-defined attributes
            # Below the additional information is added (refer to TATOR docs)

            predictions, out_img = inference.run_inference(framefile)
           
            for prediction in predictions:

                prediction['media_id'] = media_id
                prediction['type'] = None # Type ID, specifies localization, within TATOR
                prediction['frame'] = frame_number

                localizations.append(prediction)

        frame_number += 1

    # End interaction with video properly.
    vid.release()

    logger.info(f"Uploading object detections on {media.name}...")

    # Create the localizations in the video.
    num_created = 0
    for response in tator.util.chunked_create(api.create_localization_list,
                                              project_id,
                                              localization_spec=localizations):
        num_created += len(response.id)

    # Output pretty logging information.
    logger.info(f"Successfully created {num_created} localizations on "
                f"{media.name}!")

    logger.info("-------------------------------------------------")

logger.info(f"Completed inference on {len(media_ids)} files.")
