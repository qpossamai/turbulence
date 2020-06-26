import glob
import os
import pickle
import sys
import time
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
from cv2 import VideoWriter, VideoWriter_fourcc
from scipy.spatial.transform import Rotation
import scipy.integrate as integrate

from util import Progress, Transform, angle_arccos
from util2 import ABSOLUTE_PATH

major, _, _, _, _ = sys.version_info
assert major == 3


def aff3d(xyz_array, quat_array, video_path):
    assert len(xyz_array) == len(quat_array)
    print(video_path)
    x_pos = np.array([1, 0, 0])
    y_pos = np.array([0, 1, 0])
    z_pos = np.array([0, 0, 1])
    # minx, miny, minz = np.min(xyz_array, axis=0) - 1
    # maxx, maxy, maxz = np.max(xyz_array, axis=0) + 1

    width = 640
    height = 480

    codec = VideoWriter_fourcc(*'H264')
    fps = 50
    video = VideoWriter(video_path, codec, float(fps), (width, height), True)
    prg = Progress(len(xyz_array))

    for xyz, quat in zip(xyz_array, quat_array):
        tf_pos_ref = Transform().from_pos(xyz, quat).get_inv()
        x_ref = tf_pos_ref.get_rot() @ x_pos
        y_ref = tf_pos_ref.get_rot() @ y_pos
        z_ref = tf_pos_ref.get_rot() @ z_pos

        fig = plt.figure()
        ax = fig.gca(projection='3d')

        ax.quiver(xyz[0], xyz[1], xyz[2], x_ref[0], x_ref[1], x_ref[2], length=1, normalize=False, color='r')
        ax.quiver(xyz[0], xyz[1], xyz[2], y_ref[0], y_ref[1], y_ref[2], length=1, normalize=False, color='g')
        ax.quiver(xyz[0], xyz[1], xyz[2], z_ref[0], z_ref[1], z_ref[2], length=1, normalize=False, color='b')

        ax.scatter(xs=xyz[0] + 1, ys=xyz[1] + 1, zs=xyz[2] + 1, alpha=0)
        ax.scatter(xs=xyz[0] - 1, ys=xyz[1] - 1, zs=xyz[2] - 1, alpha=0)

        # ax.scatter(xs=minx, ys=miny, zs=minz, alpha=0)
        # ax.scatter(xs=maxx, ys=maxy, zs=maxz, alpha=0)

        fig.canvas.draw()
        data = np.fromstring(fig.canvas.tostring_rgb(), dtype=np.uint8, sep='').reshape((height, width, 3))

        plt.close('all')
        # plt.show()

        video.write(data[:, :, ::-1])  # Because VideoWriter.write take BGR images
        prg.update_pgr()


    video.release()
    cv2.destroyAllWindows()
    print()


class DataPreparation(object):
    def __init__(self, flight_number: int, pose_source: str):
        self.tic = time.time()

        # aff3d(np.zeros((1, 3)), np.array([0, 0, 0, 1]).reshape((1, 4)))

        self.flight_number = flight_number
        # Import data
        flight_files = []
        i = 0
        for day in sorted(next(os.walk(ABSOLUTE_PATH))[1]):
            temp_path = ABSOLUTE_PATH + day + '/'
            for flight_name in sorted(next(os.walk(temp_path))[1]):
                flight_path = temp_path + flight_name + '/'
                if i == self.flight_number:
                    self.flight_name = day + '/' + flight_name + '/'
                    for filepath in sorted(glob.glob(flight_path + '*.npy')):
                        flight_files.append(filepath)
                    for filepath in sorted(glob.glob(flight_path + '*.pkl')):
                        flight_files.append(filepath)
                    flight_files = sorted(flight_files)
                i += 1
        if pose_source == 'tubex_estimator':
            self.camera_info_left = pickle.load(open(flight_files[1], 'rb'), encoding='latin1')
            self.camera_info_right = pickle.load(open(flight_files[2], 'rb'), encoding='latin1')
            self.left_frames = np.load(flight_files[3])
            self.left_frames_time = np.load(flight_files[4])
            self.right_frames = np.load(flight_files[5])
            self.right_frames_time = np.load(flight_files[6])
            self.poses_data = pickle.load(open(flight_files[7], 'rb'), encoding='latin1')

        elif pose_source == 'imu':
            self.camera_info_left = pickle.load(open(flight_files[1], 'rb'), encoding='latin1')
            self.camera_info_right = pickle.load(open(flight_files[2], 'rb'), encoding='latin1')
            self.left_frames = np.load(flight_files[3])
            self.left_frames_time = np.load(flight_files[4])
            self.right_frames = np.load(flight_files[5])
            self.right_frames_time = np.load(flight_files[6])
            imu = pickle.load(open(flight_files[0], 'rb'), encoding='latin1')

            # angular velocity integration to quaternions
            quat = np.zeros((len(imu['orientation']), 4))
            quat[0][3] = 1

            ts = imu['time'][1:] - imu['time'][:-1]
            for i, (wx, wy, wz) in enumerate(imu['angular_velocity'][:-1]):
                mat = np.eye(4) + 1 / 2 * ts[i] * np.array([[0, -wx, -wy, -wz],
                                                            [wx, 0, wz, -wy],
                                                            [wy, -wz, 0, wx],
                                                            [wz, wy, -wx, 0]])
                quat[i + 1] = (mat @ quat[i].reshape((4, 1))).flatten()
                quat[i+1] /= np.linalg.norm(quat[i+1])

            # linear acceleration correction
            g = 9.81
            imu['linear_acceleration'] = -imu['linear_acceleration']  # gravity is positive
            for i, xyz in enumerate(imu['linear_acceleration']):
                tf_ref_drone = Transform().from_pos(np.zeros(3), quat[i])

                pass

            # linear acceleration double integration to position
            velocity = np.zeros_like(imu['linear_acceleration'])
            xyz = np.zeros_like(imu['linear_acceleration'])
            for i in range(3):
                velocity[:, i] = integrate.cumtrapz(y=imu['linear_acceleration'][:, i], x=imu['time'], initial=0.)
                xyz[:, i] = integrate.cumtrapz(y=velocity[:, i], x=imu['time'], initial=0.)

            name = ABSOLUTE_PATH + 'integration_videos/' + 'integration.mkv'
            aff3d(xyz, quat, video_path=name)
            sys.exit(0)

            self.poses_data = {'time': new_imu_time,
                               'xyz': xyz,
                               'quaternions': quat,
                               'cov': imu['linear_acceleration_cov']}

        self.frames_height = self.left_frames.shape[1]
        self.frames_width = self.left_frames.shape[2]
        self.frames_time = None

        self.tac = time.time()
        print(f'Primary import done | Time since beginning : {self.tac - self.tic:.03f}s |'
              f' Time since last step : {self.tac - self.tic:.03f}s')
        self.toc = time.time()

    def time_analysis(self):
        poses_time = self.poses_data['time']
        frames_time = self.left_frames_time

        plt.plot(poses_time, np.zeros(len(poses_time)), label='pose')
        plt.plot(frames_time, np.zeros(len(frames_time)) + 1, label='frames')
        plt.legend()
        plt.title(self.flight_name)
        plt.show()
        print(self.flight_name)
        print(f'Nb of poses : {len(poses_time)}')
        print(f'Nb of frames : {len(frames_time)}')
        print()

    def fusion(self):

        # Nan verification FOLD
        poses_time = self.poses_data['time'].copy()
        x = np.sum(np.isnan(poses_time))
        assert x == 0

        poses_xyz = self.poses_data['pose']['xyz'].copy()
        x = np.sum(np.isnan(poses_xyz))
        assert x == 0

        poses_quaternions = self.poses_data['pose']['quaternions'].copy()
        # poses_quaternions[0, :] = [0, 0, 0, 0]  # Init first quaternions
        ind = [i for i, x in enumerate(np.isnan(poses_quaternions)) if not any(x)]
        poses_quaternions = poses_quaternions[ind]
        poses_xyz = poses_xyz[ind]
        poses_time = poses_time[ind]
        x = np.sum(np.isnan(poses_quaternions))
        assert x == 0
        self.poses_data['pose']['quaternions'] = poses_quaternions.copy()

        poses_cov = self.poses_data['pose']['cov'].copy()
        x = np.sum(np.isnan(poses_cov))
        assert x == 0

        assert len(self.left_frames_time) == len(np.unique(self.left_frames_time))
        x = np.sum(np.isnan(self.left_frames_time))
        assert x == 0

        assert len(self.right_frames_time) == len(np.unique(self.right_frames_time))
        x = np.sum(np.isnan(self.right_frames_time))
        assert x == 0

        x = np.sum(np.isnan(self.left_frames))
        assert x == 0
        assert self.frames_height < self.frames_width

        x = np.sum(np.isnan(self.right_frames))
        assert x == 0
        assert self.right_frames.shape[1] == self.frames_height
        assert self.right_frames.shape[2] == self.frames_width

        self.tac = time.time()
        print(f'Nan finished | Time since beginning : {self.tac - self.tic:.03f}s |'
              f' Time since last step : {self.tac - self.toc:.03f}s')
        self.toc = time.time()

        # Intersection between time arrays and sorting them in chronological order FOLD
        self.frames_time, left_ind, right_ind = np.intersect1d(self.left_frames_time, self.right_frames_time,
                                                               assume_unique=True, return_indices=True)
        self.left_frames = self.left_frames[left_ind]
        self.right_frames = self.right_frames[right_ind]

        # Chronological order
        poses_ind = np.argsort(poses_time)
        poses_time = poses_time[poses_ind]
        poses_xyz = poses_xyz[poses_ind]
        poses_quaternions = poses_quaternions[poses_ind]

        self.tac = time.time()
        print(f'Chronological order & Left right merge | Time since beginning : {self.tac - self.tic:.03f}s '
              f'| Time since last step : {self.tac - self.toc:.03f}s')
        self.toc = time.time()

        # Time normalization
        assert np.min(self.frames_time) < np.min(poses_time)

        t0 = np.min(self.left_frames_time)
        self.frames_time = self.frames_time - t0
        poses_time = poses_time - t0

        self.tac = time.time()
        print(f'Time normalization | Time since beginning : {self.tac - self.tic:.03f}s |'
              f' Time since last step : {self.tac - self.toc:.03f}s')
        self.toc = time.time()

        # Merge poses time and frames time FOLD
        new_poses_time = []
        new_xyz = []
        new_quaternions = []
        new_left_frames = []
        new_right_frames = []
        new_cov = []
        frames_ids = []
        poses_ids = []
        for i, p_time in enumerate(poses_time):
            mini_ind = 0
            mini = abs(self.frames_time[0] - p_time)
            for j, f_time in enumerate(self.frames_time):
                diff = abs(f_time - p_time)
                if mini > diff:
                    mini_ind = j
                    mini = diff
            if (mini_ind not in frames_ids) and (i not in poses_ids):
                new_poses_time.append(poses_time[i])
                new_xyz.append(poses_xyz[i])
                new_quaternions.append(poses_quaternions[i])
                new_left_frames.append(self.left_frames[mini_ind])
                new_right_frames.append(self.right_frames[mini_ind])
                new_cov.append(poses_cov[i])

                frames_ids.append(mini_ind)
                poses_ids.append(i)

        (self.poses_data['time'], self.poses_data['pose']['xyz'], self.poses_data['pose']['quaternions'],
         self.left_frames, self.right_frames, self.poses_data['pose']['cov']) = map(np.asarray, [new_poses_time,
                                                                                                 new_xyz,
                                                                                                 new_quaternions,
                                                                                                 new_left_frames,
                                                                                                 new_right_frames,
                                                                                                 new_cov])

        self.tac = time.time()
        print(f'Fusion left & right frames with poses |'
              f' Time since beginning : {self.tac - self.tic:.03f}s |'
              f' Time since last step : {self.tac - self.toc:.03f}s')
        self.toc = time.time()

        clean_data = {'time': self.poses_data['time'],
                      'xyz': self.poses_data['pose']['xyz'],
                      'quaternions': self.poses_data['pose']['quaternions'],
                      'cov': self.poses_data['pose']['cov'],
                      'left_frames': self.left_frames,
                      'right_frames': self.right_frames,
                      'camera_info_right': self.camera_info_right,
                      'camera_info_left': self.camera_info_left}

        path = ABSOLUTE_PATH + self.flight_name + 'clean_data/'
        Path(path).mkdir(parents=True, exist_ok=True)
        pickle.dump(clean_data, open(path + 'data.pkl', 'wb'))
        print()

        # poses_time = self.poses_data['time']
        #
        # poses_time_before = poses_time[:-1]
        # poses_time_after = poses_time[1:]
        # diff = poses_time_after - poses_time_before
        # plt.plot(poses_time_after, diff, '.')
        # plt.title('Poses timestamp difference')
        # plt.xlabel('Timestamp')
        # plt.ylabel('Time difference')
        # plt.show()

        # frames_time_before = self.left_frames_time[:-1]
        # frames_time_after = self.left_frames_time[1:]
        # diff = frames_time_after - frames_time_before
        # plt.plot(frames_time_after, diff, '.')
        # plt.title('Frames timestamp difference')
        # plt.xlabel('Timestamp')
        # plt.ylabel('Time difference')
        # plt.show()
        #
        # right_frames_time_before = self.right_frames_time[:-1]
        # right_frames_time_after = self.right_frames_time[1:]
        # diff = right_frames_time_after - right_frames_time_before
        # plt.plot(right_frames_time_after, diff, '.')
        # plt.title('Right frames timestamp difference')
        # plt.xlabel('Timestamp')
        # plt.ylabel('Time difference')
        # plt.show()


class ErrorEstimation(object):
    def __init__(self, flight_number):
        self.tic = time.time()
        self.flight_number = flight_number
        # Import data
        flight_files = []
        i = 0
        for day in sorted(next(os.walk(ABSOLUTE_PATH))[1]):
            temp_path = ABSOLUTE_PATH + day + '/'
            for flight_name in sorted(next(os.walk(temp_path))[1]):
                flight_path = temp_path + flight_name + '/clean_data/'
                if i == self.flight_number:
                    self.flight_name = day + '/' + flight_name + '/'
                    for filepath in sorted(glob.glob(flight_path + '*.pkl')):
                        flight_files.append(filepath)
                    flight_files = sorted(flight_files)
                i += 1

        self.data = pickle.load(open(flight_files[0], 'rb'))

        self.time = self.data['time']
        self.xyz = self.data['xyz']
        self.quaternions = self.data['quaternions']
        self.cov = self.data['cov']
        self.left_frames = self.data['left_frames']
        self.right_frames = self.data['right_frames']
        self.camera_info_left = self.data['camera_info_left']
        self.camera_info_right = self.data['camera_info_right']

        self.frames_height = self.left_frames.shape[1]
        self.frames_width = self.left_frames.shape[2]

        self.tf_enu_flu = Transform().from_pos(self.xyz[0], self.quaternions[0])

        # Vincent input (0.105, 0, 0, -1.57, 0.0, -2.0943) (convention x, y, z, roll, pitch, yaw)
        quat = Rotation.from_euler('xyz', np.array([-120, 0, -90]), degrees=True).as_quat()
        self.tf_drone_camera = Transform().from_pos(np.array([0.105, 0, 0]), quat)

        tf_flu_enu = self.tf_enu_flu.get_inv()
        for i, (pos, quat) in enumerate(zip(self.xyz, self.quaternions)):
            tf_enu_drone = Transform().from_pos(pos, quat)
            tf_flu_drone = tf_flu_enu @ tf_enu_drone
            self.xyz[i], self.quaternions[i] = tf_flu_drone.get_pose()

        self.tac = time.time()
        print(f'Primary import done | '
              f'Time since beginning : {self.tac - self.tic:.03f}s | '
              f'Time since last step : {self.tac - self.tic:.03f}s')
        self.toc = time.time()

    def get_camera_angle_to_horizontal_plane(self, iteration):
        z_camera_in_camera = np.array([0, 0, 1])  # Vector only rotation are important and NOT translations

        tf_camera_drone = self.tf_drone_camera.get_inv()
        rot_camera_drone = tf_camera_drone.get_rot()
        z_camera_in_drone = rot_camera_drone @ z_camera_in_camera

        tf_flu_drone = Transform().from_pos(self.xyz[iteration], self.quaternions[iteration])
        tf_drone_flu = tf_flu_drone.get_inv()
        rot_drone_flu = tf_drone_flu.get_rot()
        z_camera_in_flu = (rot_drone_flu @ z_camera_in_drone)[:3]

        res = np.arcsin(np.abs(z_camera_in_flu[2]) / np.linalg.norm(z_camera_in_flu))
        return res

    def image23d(self, idx, image_point):
        # self.xyz and self.quaternions are from FLU to Drone

        p_left = self.camera_info_left['P']
        fx = p_left[0, 0]
        fy = p_left[1, 1]
        cx = p_left[0, 2]
        cy = p_left[1, 2]

        image_x = image_point[0]
        image_y = image_point[1]
        temp_z = 10
        x = (temp_z / fx) * (image_x - cx)
        y = (temp_z / fy) * (image_y - cy)
        vect1 = np.array([x, y, temp_z])

        middle_x = cx
        middle_y = cy
        x = (temp_z / fx) * (middle_x - cx)
        y = (temp_z / fy) * (middle_y - cy)
        vect2 = np.array([x, y, temp_z])
        pixel_angle = angle_arccos(vect1, vect2) * 180 / np.pi

        # pixel_angle = 8.34  # ° between optical center (cx, cy) and (cx, cy + cy / 2)

        camera_angle_to_horizontal_plane = self.get_camera_angle_to_horizontal_plane(idx) * 180 / np.pi
        theta = (camera_angle_to_horizontal_plane + pixel_angle) * np.pi / 180

        h = np.round(self.xyz[idx][2], 3)
        h = (h if h > 0 else 0) + 0.1  # Todo to complete

        true_z = h / np.cos(np.pi / 2 - theta)

        x = (true_z / fx) * (image_x - cx)
        y = (true_z / fy) * (image_y - cy)

        return np.array([x, y, true_z, 1]).reshape((4, 1))

    def _is_out_of_image(self, image_point):
        assert len(image_point) == 2
        a = image_point
        return not ((0 <= a[0] < self.frames_width) and (0 <= a[1] < self.frames_height))

    def _space2image(self, point3d):
        p_matrix = self.camera_info_left['P']
        u, v, w = np.dot(p_matrix, point3d).flatten()
        return u / w, v / w

    def p3_generator(self):
        r0 = {'xyz': self.xyz[0], 'quat': self.quaternions[0]}  # in Reference Frame flu to drone
        r1 = r0
        cx, cy = self.camera_info_left['P'][0, 2], self.camera_info_left['P'][1, 2]
        p = (cx, cy + cy / 2)
        p1 = self.image23d(0, p)
        p3_list = []
        for i in range(len(self.time)):
            ri = {'xyz': self.xyz[i], 'quat': self.quaternions[i]}
            tf_flu_r1cam = Transform().from_pos(r1['xyz'], r1['quat']) @ self.tf_drone_camera
            tf_flu_ricam = Transform().from_pos(ri['xyz'], ri['quat']) @ self.tf_drone_camera
            tf_r1cam_ricam = tf_flu_r1cam.get_inv() @ tf_flu_ricam
            p2 = tf_r1cam_ricam @ p1
            p3 = self._space2image(p2)
            if self._is_out_of_image(p3):
                r1 = {'xyz': self.xyz[i], 'quat': self.quaternions[i]}
                p1 = self.image23d(i, p)  # RF camera
                p3 = (40, 40)
            p3_list.append(p3)
        self.data['p3'] = p3_list
        pickle.dump(self.data, open(ABSOLUTE_PATH + self.flight_name + 'clean_data/data.pkl', 'wb'))

    def p32video(self):
        fps = 10
        codec = VideoWriter_fourcc(*'H264')
        part1, part2, _ = self.flight_name.split('/')
        name = ABSOLUTE_PATH + 'error_estimation_videos/' + part1 + '_' + part2 + '_error_estimation.mkv'
        video = VideoWriter(name, codec, float(fps), (self.frames_width, self.frames_height), True)
        print(name)

        frames = self.left_frames
        prg = Progress(len(frames))
        point_list = self.data['p3']
        shape = (self.frames_height, self.frames_width, 3)
        for i, frame in enumerate(frames):
            p = np.int32(np.round(point_list[i]))
            color_frame = np.uint8(np.zeros((self.frames_height, self.frames_width, 3)))
            for j in range(3):
                color_frame[:, :, j] = frame
            fig = plt.figure()
            ax = plt.axes([0, 0, 1, 1])
            plt.imshow(color_frame)
            angles = Rotation.from_quat(self.quaternions[i]).as_euler('xyz', degrees=True)
            plt.scatter(p[0], p[1], color='r')
            legend = (f'Drone pose - FLU\n'
                      f'      x : {self.xyz[i][0]:8.3f}m\n'
                      f'      y : {self.xyz[i][1]:8.3f}m\n'
                      f'      z : {self.xyz[i][2]:8.3f}m\n'
                      f'Rot x : {angles[0]:8.3f}°\n'
                      f'Rot y : {angles[1]:8.3f}°\n'
                      f'Rot z : {angles[2]:8.3f}°')
            plt.annotate(legend, (450, 335), xycoords='axes points', size=12, ha='right', va='top',
                         bbox=dict(boxstyle='round', alpha=0.5, fc='w'))
            ax.axis('off')
            fig.canvas.draw()
            data = np.fromstring(fig.canvas.tostring_rgb(), dtype=np.uint8, sep='').reshape(shape)
            plt.close('all')

            video.write(data[:, :, ::-1])  # Because VideoWriter.write take BGR images
            prg.update_pgr()

        video.release()
        cv2.destroyAllWindows()
        # del video


if __name__ == '__main__':
    def main():
        # pose_source possibilities : ['tubex_estimator, imu']
        e = DataPreparation(flight_number=0, pose_source='imu')
        e.fusion()
        # for flight_number in range(0, 12):
        #     if flight_number == 1:
        #         continue
        #     print(flight_number)
        #     e = DataPreparation(flight_number=flight_number)
        #     e.fusion()

        # for flight_number in range(0, 12):
        #     if flight_number == 1:
        #         continue
        #     f = ErrorEstimation(flight_number=flight_number)
        #     f.p3_generator()
        #     f.p32video()


    main()
