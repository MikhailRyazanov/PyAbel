# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import numpy as np
import abel
from . import basex
from . import dasch
from . import direct
from . import linbasex
from . import hansenlaw
from . import onion_bordas
from . import tools


class AbelTiming(object):
    def __init__(self, n=[301, 501], select=['all', ], n_max_bs=700,
                 n_max_slow=700, transform_repeat=1):
        """
        Benchmark performance of different iAbel/fAbel implementations.

        Parameters
        ----------
        n: integer
            a list of arrays sizes for the benchmark
            (assuming 2D square arrays (n,n))

        select: list of str
            list of transforms to benchmark select=['all',] (default) or
            choose transforms:
            select=['basex', 'basex(var)', 'direct_Python', 'direct_C',
                    'hansenlaw', 'linbasex' 'onion_bordas, 'onion_peeling',
                    'two_point', 'three_point']

        n_max_bs: integer
            since the basis sets generation takes a long time,
            do not run this benchmark for implementations that use basis sets
            for n > n_max_bs

        n_max_slow: integer
            maximum n run for the "slow" transform methods, so far including
            only the "direct_python" implementation.
        """
        from timeit import Timer, default_timer
        import time

        self.n = n

        # (expression "f1() and False or f2()" ensures that f1() is called
        #  before f2() and that the overall result is f2())
        transform = {
            'basex': basex.basex_core_transform,
            'basex(var)': lambda IM, _: basex.basex_core_transform(IM,
                                            basex.get_bs_cached(IM.shape[1],
                                               reg=1.0+np.random.random(),
                                               basis_dir=None)),
                                        # force updating regularization every
                                        # time (basis itself is cached)
            'basex_bs': lambda w: basex.cache_cleanup() and False or
                                  basex.get_bs_cached(w, basis_dir=None),
            'direct_Python': direct.direct_transform,
            'direct_C': direct.direct_transform,
            'hansenlaw': hansenlaw.hansenlaw_transform,
            'linbasex': linbasex._linbasex_transform_with_basis,
            'linbasex_bs': lambda w: linbasex.cache_cleanup() and False or
                                     linbasex._bs_linbasex(2 * w - 1),
                                     # linbasex needs full width
            'onion_bordas': onion_bordas.onion_bordas_transform,
            'onion_peeling': dasch.dasch_transform,
            'onion_peeling_bs': lambda w: dasch.cache_cleanup() and False or
                                          dasch._bs_onion_peeling(w),
            'two_point': dasch.dasch_transform,
            'two_point_bs': lambda w: dasch.cache_cleanup() and False or
                                      dasch._bs_two_point(w),
            'three_point': dasch.dasch_transform,
            'three_point_bs': lambda w: dasch.cache_cleanup() and False or
                                        dasch._bs_three_point(w),
        }

        # result dicts
        res = {}
        res['bs'] = {'basex_bs': [], 'linbasex_bs': [], 'onion_peeling_bs': [],
                     'two_point_bs': [], 'three_point_bs': []}
        res['forward'] = {'direct_Python': [], 'hansenlaw': []}
        res['inverse'] = {'basex': [], 'basex(var)': [], 'direct_Python': [],
                          'hansenlaw': [], 'linbasex': [],
                          'onion_bordas': [], 'onion_peeling': [],
                          'two_point': [], 'three_point': []}

        if direct.cython_ext:
            res['forward']['direct_C'] = []
            res['inverse']['direct_C'] = []

        # delete all keys not present in 'select' input parameter
        if 'all' not in select:
            for trans in select:
                if trans not in res['inverse'].keys():
                    raise ValueError('"{}" is not a valid transform method'.
                                     format(trans), res['inverse'].keys())

            for direction in ['forward', 'inverse']:
                rm = []
                for abel in res[direction]:
                    if abel not in select:
                        rm.append(abel)
                for x in rm:
                    del res[direction][x]
            # repeat for 'bs' which has append '_bs'
            rm = []
            select_b = [m.split('(')[0] for m in select]  # before parentheses
            for abel in res['bs']:
                if abel[:-3] not in select_b:
                    rm.append(abel)
            for x in rm:
                del res['bs'][x]

        # ---- timing tests for various image sizes nxn
        for ni in n:
            ni = int(ni)
            h, w = ni, ni//2 + 1
            # We transform a rectangular image, since we are making the assumption
            # that we are transforming just the "right side" of a square image.
            # see: https://github.com/PyAbel/PyAbel/issues/207

            half_image  = np.random.randn(h, w)
            whole_image = np.random.randn(h, h)
            # basis set evaluation --------------
            basis = {}
            for method in res['bs'].keys():
                if ni <= n_max_bs:
                    # calculate and store basis matrix
                    t = default_timer()
                    basis[method[:-3]] = transform[method](w)
                    res['bs'][method].append((default_timer() - t) * 1000)
                else:
                    basis[method[:-3]] = None,
                    res['bs'][method].append(np.nan)

            # Abel transforms ---------------
            for cal in ['forward', 'inverse']:
                for method in res[cal].keys():
                    method_b = method.split('(')[0]  # part before parentheses
                    if method_b in basis.keys():
                        if basis[method_b][0] is not None:
                            # have basis calculation
                            if method == 'linbasex':
                                # pass a whole image to linbasex
                                IM = whole_image
                            else:
                                IM = half_image
                            res[cal][method].append(Timer(
                               lambda: transform[method](IM, basis[method_b])).
                               timeit(number=transform_repeat) * 1000 /
                               transform_repeat)
                        else:
                            # no calculation available
                            res[cal][method].append(np.nan)
                    elif method[:6] == 'direct':  # special case 'direct'
                        if method[7] == 'P' and (ni > n_max_slow):
                            res[cal][method].append(np.nan)
                        else:
                            res[cal][method].append(Timer(
                               lambda: transform[method](half_image, backend=method[7:],
                                                         direction=cal)).
                               timeit(number=transform_repeat) * 1000 /
                               transform_repeat)
                    else:
                        # full calculation for everything else
                        res[cal][method].append(Timer(
                           lambda: transform[method](half_image, direction=cal)).
                           timeit(number=transform_repeat) * 1000 /
                           transform_repeat)

        self.fabel = res['forward']
        self.bs = res['bs']
        self.iabel = res['inverse']

    def __repr__(self):
        import platform
        from itertools import chain

        out = []
        out += ['PyAbel benchmark run on {}\n'.format(platform.processor())]
        out += ['time in milliseconds']

        LABEL_FORMAT = 'Implementation  ' +\
                       ''.join(['    n = {:<9} '.format(ni) for ni in self.n])
        ROW_FORMAT = '{:>16} ' + ' {:8.1f}         '*len(self.n)
        SEP_ROW = '' + '-'*(22 + (17+1)*len(self.n))

        HEADER_ROW = '\n========= {:>8} Abel implementations ==========\n'

        def print_benchmark(name, res):
            out = [HEADER_ROW.format(name)]
            if res:
                out += [LABEL_FORMAT]
                out += [SEP_ROW]
                for name, row in sorted(res.items()):
                    out += [ROW_FORMAT.format(name, *row)]
            return out

        out += print_benchmark('Basis', self.bs)
        out += ['']
        out += print_benchmark('Forward', self.fabel)
        out += ['']
        out += print_benchmark('Inverse', self.iabel)
        return '\n'.join(out)


def is_symmetric(arr, i_sym=True, j_sym=True):
    """
    Takes in an array of shape (n, m) and check if it is symmetric

    Parameters
    ----------
    arr : 1D or 2D array
    i_sym : array
        symmetric with respect to the 1st axis
    j_sym : array
        symmetric with respect to the 2nd axis

    Returns
    -------
    a binary array with the symmetry condition for the corresponding quadrants.
    The globa

    Note: if both i_sym=True and i_sym=True, the input array is checked
    for polar symmetry.

    See https://github.com/PyAbel/PyAbel/issues/34#issuecomment-160344809
    for the defintion of a center of the image.
    """

    Q0, Q1, Q2, Q3 = tools.symmetry.get_image_quadrants(
                                                 arr, reorient=False)

    if i_sym and not j_sym:
        valid_flag = [np.allclose(np.fliplr(Q1), Q0),
                      np.allclose(np.fliplr(Q2), Q3)]
    elif not i_sym and j_sym:
        valid_flag = [np.allclose(np.flipud(Q1), Q2),
                      np.allclose(np.flipud(Q0), Q3)]
    elif i_sym and j_sym:
        valid_flag = [np.allclose(np.flipud(np.fliplr(Q1)), Q3),
                      np.allclose(np.flipud(np.fliplr(Q0)), Q2)]
    else:
        raise ValueError('Checking for symmetry with both i_sym=False \
                          and j_sym=False does not make sense!')

    return np.array(valid_flag)


def absolute_ratio_benchmark(analytical, recon, kind='inverse'):
    """
    Check the absolute ratio between an analytical function and the result
    of a inv. Abel reconstruction.

    Parameters
    ----------
    analytical : one of the classes from analytical, initialized

    recon : 1D ndarray
        a reconstruction (i.e. inverse abel)
        given by some PyAbel implementation
    """
    mask = analytical.mask_valid

    if kind == 'inverse':
        func = analytical.func
    elif kind == 'forward':
        func = analytical.abel

    err = func[mask]/recon[mask]
    return err
