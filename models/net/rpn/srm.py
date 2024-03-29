# --------------------------------------------------------
# Two Stream Faster R-CNN
# Licensed under The MIT License [see LICENSE for details]
# Written by Hangyan Jiang
# --------------------------------------------------------

# Testing part
import torch
import torch.nn as nn
import torch.nn.functional as F
import cv2
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt

# 将输入图片归一化
def PlotImage(image):
    """
	PlotImage: Give a normalized image matrix which can be used with implot, etc.
	Maps to [0, 1]
	"""
    im = image.astype(float)
    return (im - np.min(im)) / (np.max(im) - np.min(im))

def SRM(imgs):
    # 第一层滤波器
    # 定义三个滤波器,滤波器大小为5x5
    # filter1: egde3*3
    filter3 = [[0, 0, 0, 0, 0],
               [0, -1, 2, -1, 0],
               [0, 2, -4, 2, 0],
               [0, -1, 2, -1, 0],
               [0, 0, 0, 0, 0]]
    # filter2：egde5*5
    filter2 = [[-1, 2, -2, 2, -1],
               [2, -6, 8, -6, 2],
               [-2, 8, -12, 8, -2],
               [2, -6, 8, -6, 2],
               [-1, 2, -2, 2, -1]]
    # filter3：一阶线性
    filter1 = [[0, 0, 0, 0, 0],
               [0, 0, 0, 0, 0],
               [0, 1, -2, 1, 0],
               [0, 0, 0, 0, 0],
               [0, 0, 0, 0, 0]]
    # 定义q，将三个滤波器归一化
    q = [4.0, 12.0, 2.0]
    filter1 = np.asarray(filter1, dtype=float) / 4
    filter2 = np.asarray(filter2, dtype=float) / 12
    filter3 = np.asarray(filter3, dtype=float) / 2
    # 将不同类的滤波器堆叠、处理，得到新滤波器
    filters = [[filter1, filter1, filter1], [filter2, filter2, filter2], [filter3, filter3, filter3]]# (3,3,5,5)
    #filters = np.einsum('klij->ijlk', filters)  # new_filter(i,j,l,k) = origin_filter(k,l,i,j) # (5,5,3,3)
    filters = torch.FloatTensor(filters)    # (3,3,5,5)
    imgs = np.array(imgs, dtype=float)  # (375,500,3)
    #imgs = imgs[:, :, np.newaxis, :]
    imgs = np.einsum('klij->kjli', imgs)
    input = torch.tensor(imgs, dtype=torch.float32)
    # 未标出的卷积参数：use_cudnn_on_gpu=True, data_format="NHWC", dilations=[1, 1, 1, 1], name=None
    # 得到第一层输出：op
    #op = tf.nn.conv2d(input, filters, strides=[1, 1, 1, 1], padding='SAME')
    op = F.conv2d(input, filters, stride=1, padding=2)

    # 定义第二层滤波器，滤波方式同第一层
    q = [4.0, 12.0, 2.0]
    # filter1: egde3*3
    filter3 = [[0, 0, 0, 0, 0],
               [0, -1, 2, -1, 0],
               [0, 2, -4, 2, 0],
               [0, -1, 2, -1, 0],
               [0, 0, 0, 0, 0]]
    # filter2：egde5*5
    filter2 = [[-1, 2, -2, 2, -1],
               [2, -6, 8, -6, 2],
               [-2, 8, -12, 8, -2],
               [2, -6, 8, -6, 2],
               [-1, 2, -2, 2, -1]]
    # filter3：一阶线性
    filter1 = [[0, 0, 0, 0, 0],
               [0, 0, 0, 0, 0],
               [0, 1, -2, 1, 0],
               [0, 0, 0, 0, 0],
               [0, 0, 0, 0, 0]]
    filter1 = np.asarray(filter1, dtype=float) / q[0]
    filter2 = np.asarray(filter2, dtype=float) / q[1]
    filter3 = np.asarray(filter3, dtype=float) / q[2]
    filters = [[filter1, filter1, filter1], [filter2, filter2, filter2], [filter3, filter3, filter3]]# (3,3,5,5)
    #filters = np.einsum('klij->ijlk', filters)                          # (5,5,3,3)
    #filters = filters.flatten()     # 将filters拉成一维 (225,)
    #initializer_srm = tf.constant_initializer(filters)
    filters = torch.tensor(filters,dtype=torch.float32,requires_grad=False)

    # 分段函数:     x < -2, y = -2;     -2 < x < 2, y = x;     x > 2, y = 2
    def truncate_2(x):
        neg = ((x + 2) + abs(x + 2)) / 2 - 2
        return -(-neg+2 + abs(- neg+2)) / 2 + 2

    # 卷积参数：
    # inputs = input = tf.Variables(img),    num_outputs = 3,    kernel_size = 5 x 5,    rate = 1
    # op2 = slim.conv2d(input, 3, [5, 5], trainable=False, weights_initializer=initializer_srm,
    #                   activation_fn=None, padding='SAME', stride=1, scope='srm')
    # op2 = truncate_2(op2)
    # 将op2用(-2, 2)的分段函数激活
    # 得到第二层输出：op2
    op2 = F.conv2d(input, filters, stride=1, padding=2)
    print('op2\'s shape', op2.shape)

    # 定义第三层滤波器
    filter_coocurr = [[0, 0, 0, 0, 0, 0, 0],
                      [0, 0, 0, 0, 0, 0, 0],
                      [0, 0, 0, 0, 0, 0, 0],
                      [0, 0, 0, 1, 1, 1, 1],
                      [0, 0, 0, 1, 0, 0, 0],
                      [0, 0, 0, 1, 0, 0, 0],
                      [0, 0, 0, 1, 0, 0, 0]]
    filter_coocurr_zero = [[0, 0, 0, 0, 0, 0, 0],
                           [0, 0, 0, 0, 0, 0, 0],
                           [0, 0, 0, 0, 0, 0, 0],
                           [0, 0, 0, 0, 0, 0, 0],
                           [0, 0, 0, 0, 0, 0, 0],
                           [0, 0, 0, 0, 0, 0, 0],
                           [0, 0, 0, 0, 0, 0, 0]]
    # filters_coocurr: 3 x 3 x 7 x 7
    filters_coocurr = [[filter_coocurr, filter_coocurr_zero, filter_coocurr_zero],
                       [filter_coocurr_zero, filter_coocurr, filter_coocurr_zero],
                       [filter_coocurr_zero, filter_coocurr_zero, filter_coocurr]]
    #filters_coocurr = np.einsum('klij->ijlk', filters_coocurr)
    # filters_coocurr: 7 x 7x 3 x 3
    # 形似filter_coocurr的分块矩阵

    # with tf.Session() as sess:
    #     sess.run(tf.initialize_all_variables())
    #     # op：第一层的卷积输出；op2：第二层的卷积输出
    #     re = (sess.run(op))
    #     res = np.round(re[0])
    #     res[res > 2] = 2
    #     res[res < -2] = -2

    #     res2 = sess.run(op2)
        # print(sum(sum(sum(sum(res2>2)))))
    res = np.round(op[0])
    print('res\'s shape', res.shape)
    res[res > 2] = 2
    res[res < -2] = -2
    res2 = op2[0]

    ress = np.array(res, dtype=float)
    ress2 = np.array(res2, dtype=float)
    # input = tf.Variable(ress, dtype=tf.float32)
    # op = tf.nn.conv2d(input, filters_coocurr, strides=[1, 1, 1, 1], padding='SAME')
    # with tf.Session() as sess:
    #     sess.run(tf.initialize_all_variables())
    #     res = (sess.run(op))
    return ress, ress2


if __name__ == '__main__':
    img = Image.open('/home/duxiaowey/my_ps/experiments/000009.jpg')
    img = np.asarray(img)
    img, img2 = SRM([img])
    # img，img2为第一层、第二层滤波器提取后的特征图
    # img = np.sqrt(img)
    # print(img[0])
    # img = Image.fromarray(np.uint8(img[0]))
    # img.show()
    # img[0, :, :, 0] = PlotImage(img[0, :, :, 0])
    # img[0, :, :, 1] = PlotImage(img[0, :, :, 1])
    # img[0, :, :, 2] = PlotImage(img[0, :, :, 2])

    # img.shape = (1, 375, 500, 3)
    plt.imshow(img2[0])
    plt.savefig('img_op2.jpg')

    plt.imshow(PlotImage(img[0]))
    plt.savefig('img_op.jpg')

    # plt.imshow(img[0])
    # plt.show()