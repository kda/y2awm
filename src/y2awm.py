#!/usr/bin/env python3

import argparse
import json
import logging
import os
import subprocess

from enum import Enum, auto

# eventually one for each space (AND from config file)
class desktopLayout:
    class Layout(Enum):
        unknown = auto()
        left = auto()
        right = auto()
        columns = auto()
        even = auto()
        disabled = auto()

        @staticmethod
        def fromStr(layout):
            if layout == 'left':
                return desktopLayout.Layout.left
            elif layout == 'right':
                return desktopLayout.Layout.right
            elif layout == 'columns':
                return desktopLayout.Layout.columns
            elif layout == 'even':
                return desktopLayout.Layout.even
            elif layout == 'disabled':
                return desktopLayout.Layout.disabled
            else:
                return desktopLayout.Layout.unknown

    def __init__(self, layout=Layout.left, percent=70):
        self.layout_ = layout
        self.percent_ = percent

    def toJson(self):
        dl = {
                'layout': self.layout_.name,
                'percent': self.percent_,
                }
        return dl

    @staticmethod
    def fromJson(d):
        return desktopLayout(desktopLayout.Layout.fromStr(d['layout']), d['percent'])

    def isEven(self):
        return self.layout_ == self.Layout.even

    def isColumns(self):
        return self.layout_ == self.Layout.columns

    def isLeft(self):
        return self.layout_ == self.Layout.left

    def isRight(self):
        return self.layout_ == self.Layout.right

    def isDisabled(self):
        return self.layout_ == self.Layout.disabled

class configFile:
    def __init__(self):
        self.desktopLayouts_ = {}
        self.filename_ = os.path.join(os.environ['HOME'], '.config/y2awm/config.json')
        self.__load()

    def __load(self):
        self.config_ = {}
        if not os.access(self.filename_, os.R_OK | os.W_OK):
            logging.debug(f'file does not exist: {self.filename_}')
            return
        f = open(self.filename_)
        config = json.load(f)
        f.close()
        self.desktopLayouts_ = {}
        for dl in config['desktopLayouts']:
            spaceIdx = dl['spaceIdx']
            self.desktopLayouts_[spaceIdx] = desktopLayout.fromJson(dl['desktopLayout'])

    def __write(self):
        config = {
                'desktopLayouts': [],
                }
        for (spaceIdx, dl) in self.desktopLayouts_.items():
            jsonDL = {
                    'spaceIdx': spaceIdx,
                    'desktopLayout': dl.toJson(),
                    }
            config['desktopLayouts'].append(jsonDL)

        os.makedirs(os.path.dirname(self.filename_), mode=0o755, exist_ok=True)
        with open(self.filename_, "w") as outfile:
            json.dump(config, outfile)

    def getDesktopLayout(self, spaceIdx):
        if spaceIdx not in self.desktopLayouts_:
            return desktopLayout()
        return self.desktopLayouts_[spaceIdx]

    def setDesktopLayout(self, spaceIdx, layout):
        if spaceIdx not in self.desktopLayouts_:
            self.desktopLayouts_[spaceIdx] = desktopLayout()
        self.desktopLayouts_[spaceIdx].layout_ = layout
        self.__write()

    def setDesktopLayoutPercent(self, spaceIdx, percent):
        if spaceIdx not in self.desktopLayouts_:
            self.desktopLayouts_[spaceIdx] = desktopLayout()
        self.desktopLayouts_[spaceIdx].percent_ = percent
        self.__write()

class yabaiQuick:
    def __init__(self):
        self.binName_ = '/usr/local/bin/yabai'
        self.parameter_ = '-m'
        self.configFile_ = configFile()
        self.__purge()
        self.__load()

    def __purge(self):
        self.spaces_ = []
        self.windows_ = []
        self.displays_ = []
        self.focusSpaceIdx_ = None
        self.spaceIdxToWindowIds_ = {}
        self.windowIdToProperties_ = {}
        self.focusWindowId_ = None
        self.focusDisplayIdx_ = None

    def __load(self):
        # only do this once
        if len(self.spaces_) > 0:
            return
        # load from queries
        self.windows_ = json.loads(self.__windows())
        # walk windows
        for window in self.windows_:
            windowId = window['id']
            if window['has-focus']:
                self.focusWindowId_ = windowId
            self.windowIdToProperties_[windowId] = window
        self.spaces_ = json.loads(self.__spaces())
        for space in self.spaces_:
            if space['has-focus']:
                self.focusSpaceIdx_ = space['index']
            # only include visible windows
            windowIds = []
            for windowId in space['windows']:
                # skip dialogs
                if self.windowIdToProperties_[windowId]['subrole'] == 'AXDialog':
                    continue
                if self.windowIdToProperties_[windowId]['is-visible']:
                    windowIds.append(windowId)
            windowIds.sort(key=lambda windowId: (self.windowIdToProperties_[windowId]['frame']['y'], self.windowIdToProperties_[windowId]['frame']['x']))
            #print('==> space', space['index'])
            #for winId in windowIds:
            #    print(winId, self.windowIdToProperties_[winId]['frame']['x'], self.windowIdToProperties_[winId]['frame']['y'])
            self.spaceIdxToWindowIds_[space['index']] = windowIds
        # displays
        self.displays_ = json.loads(self.__displays())
        for display in self.displays_:
            if display['has-focus']:
                self.focusDisplayIdx_ = display['index']
                # also, use the right config

    def __send(self, args):
        allArgs = [self.binName_, self.parameter_] + args
        logging.debug(f'send: {allArgs}')
        cp = subprocess.run(allArgs, capture_output=True)
        # instead cp.check_returncode()
        if cp.returncode != 0:
            logging.error(f'command failed: {allArgs} {cp.returncode}')
            exit(cp.returncode)
        return cp.stdout

    def __query(self, args):
        return self.__send(['query'] + args)

    def __window(self, args):
        self.__send(['window'] + args)

    def __displays(self):
        return self.__query(['--displays'])

    def __spaces(self):
        return self.__query(['--spaces'])

    def __windows(self):
        return self.__query(['--windows'])

    def __grid(self, windowId, specification):
        self.__window([str(windowId), '--grid', specification])

    def __focusWindow(self, windowId):
        self.__window(['--focus', str(windowId)])

    def setFocus(self, nextWindow):
        windows = self.spaceIdxToWindowIds_[self.focusSpaceIdx_]
        if self.focusWindowId_ is None and len(windows) > 0:
            self.__focusWindow(windows[0])
            return
        nextWindowId = None
        for idx in range(len(windows)):
            if windows[idx] == self.focusWindowId_:
                if nextWindow:
                    nextIdx = (idx + 1) % len(windows)
                else:
                    nextIdx = (idx + len(windows) - 1) % len(windows)
                nextWindowId = windows[nextIdx]
                break
        if nextWindowId is None:
            return
        self.__focusWindow(nextWindowId)

    def arrangeSpaceIdx(self, spaceIdx, placeFocusWindow=False):
        windowIds = self.spaceIdxToWindowIds_[spaceIdx]
        if len(windowIds) == 0:
            return
        if len(windowIds) == 1:
            self.__grid(windowIds[0], f'1:1:0:0:1:1')
            return
        dl = self.configFile_.getDesktopLayout(spaceIdx)
        #print('dl:', dl)
        if dl.isDisabled():
            return
        if placeFocusWindow and self.focusWindowId_ in windowIds:
            windowIds.remove(self.focusWindowId_)
            if dl.isRight():
                windowIds.append(self.focusWindowId_)
            else:
                windowIds.insert(0, self.focusWindowId_)
        if dl.isColumns():
            cols = len(windowIds)
            for idx in range(cols):
                self.__grid(windowIds[idx], f'1:{cols}:{idx}:0:1:1')
        elif dl.isLeft():
            rows = len(windowIds) - 1
            self.__grid(windowIds[0], f'{rows}:100:0:0:{dl.percent_}:{rows}')
            width = 100 - dl.percent_
            for idx in range(1, len(windowIds)):
                self.__grid(windowIds[idx], f'{rows}:100:{dl.percent_}:{idx - 1}:{width}:1')
        elif dl.isRight():
            rows = len(windowIds) - 1
            width = 100 - dl.percent_
            self.__grid(windowIds[-1], f'{rows}:100:{width}:0:{dl.percent_}:{rows}')
            for idx in range(len(windowIds) - 1):
                self.__grid(windowIds[idx], f'{rows}:100:0:{idx}:{width}:1')
        elif dl.isEven():
            windowCount = len(windowIds)
            rows = 2
            columns = 1
            while (rows * columns) < windowCount:
                if columns < rows:
                    columns += 1
                else:
                    rows += 1
            windowIdx = 0
            rowIdx = 0
            colIdx = 0
            gridColCount = columns

            # first few rows may have a few less items
            while (windowCount - windowIdx) % columns != 0:
                # needlessly calculated multiple times for some layouts
                gridColCount =  columns * (columns - 1)
                for column in range(columns - 1):
                    width = int(gridColCount / (columns - 1))
                    self.__grid(windowIds[windowIdx], f'{rows}:{gridColCount}:{int(column * width)}:{rowIdx}:{width}:1')
                    windowIdx += 1
                rowIdx += 1

            # position remaining windows evenly
            width = int(gridColCount / columns)
            while windowIdx < windowCount:
                self.__grid(windowIds[windowIdx], f'{rows}:{gridColCount}:{int(colIdx * width)}:{rowIdx}:{width}:1')
                colIdx += 1
                if colIdx == columns:
                    rowIdx += 1
                    colIdx = 0
                windowIdx += 1


    def arrange(self, placeFocusWindow=False):
        self.arrangeSpaceIdx(self.focusSpaceIdx_, placeFocusWindow)

    def setLayout(self, layout):
        if layout[0] == 'c':
            self.configFile_.setDesktopLayout(self.focusSpaceIdx_, desktopLayout.Layout.columns)
        elif layout[0] == 'l':
            self.configFile_.setDesktopLayout(self.focusSpaceIdx_, desktopLayout.Layout.left)
        elif layout[0] == 'r':
            self.configFile_.setDesktopLayout(self.focusSpaceIdx_, desktopLayout.Layout.right)
        elif layout[0] == 'd':
            self.configFile_.setDesktopLayout(self.focusSpaceIdx_, desktopLayout.Layout.disabled)
        elif layout[0] == 'e':
            self.configFile_.setDesktopLayout(self.focusSpaceIdx_, desktopLayout.Layout.even)
        self.arrange(True)

    def setPercent(self, percent):
        dl = self.configFile_.getDesktopLayout(self.focusSpaceIdx_)
        if not dl.isLeft() and not dl.isRight():
            return
        newPercent = dl.percent_
        if percent[0] == '+':
            if dl.isRight():
                newPercent = newPercent + 100 - int(percent[1:])
            else:
                newPercent = newPercent + int(percent[1:])
        elif percent[0] == '-':
            if dl.isRight():
                newPercent = newPercent + int(percent[1:])
            else:
                newPercent = newPercent + 100 - int(percent[1:])
        else:
            newPercent = int(percent)
        newPercent = newPercent % 100
        if newPercent == 0:
            newPercent = 1
        elif newPercent == 100:
            newPercent = 99
        self.configFile_.setDesktopLayoutPercent(self.focusSpaceIdx_, newPercent)
        self.arrange()

    def moveWindow(self, windowId, destination):
        dl = self.configFile_.getDesktopLayout(self.focusSpaceIdx_)
        windowIds = self.spaceIdxToWindowIds_[self.focusSpaceIdx_]
        idx = windowIds.index(windowId)
        if dl.isColumns():
            if destination[0] == 'w':
                if idx > 0:
                    windowIds[idx], windowIds[idx - 1] = windowIds[idx - 1], windowIds[idx]
                    self.arrange()
            elif destination[0] == 'e':
                if idx < (len(windowIds) - 1):
                    windowIds[idx], windowIds[idx + 1] = windowIds[idx + 1], windowIds[idx]
                    self.arrange()
        elif dl.isLeft():
            if destination[0] == 'w':
                if idx > 0:
                    windowIds[idx], windowIds[0] = windowIds[0], windowIds[idx]
                    self.arrange()
            elif destination[0] == 'e':
                if idx == 0:
                    windowIds[idx], windowIds[idx + 1] = windowIds[idx + 1], windowIds[idx]
                    self.arrange()
            elif destination[0] == 'n':
                if idx > 1:
                    windowIds[idx], windowIds[idx - 1] = windowIds[idx - 1], windowIds[idx]
                    self.arrange()
            elif destination[0] == 's':
                if idx > 0 and idx < (len(windowIds) - 1):
                    windowIds[idx], windowIds[idx + 1] = windowIds[idx + 1], windowIds[idx]
                    self.arrange()
        elif dl.isRight():
            if destination[0] == 'w':
                if idx == (len(windowIds) - 1):
                    windowIds[idx], windowIds[0] = windowIds[0], windowIds[idx]
                    self.arrange()
            elif destination[0] == 'e':
                if idx < (len(windowIds) - 1):
                    windowIds[idx], windowIds[-1] = windowIds[-1], windowIds[idx]
                    self.arrange()
            elif destination[0] == 'n':
                if idx > 0 and idx < (len(windowIds) - 1):
                    windowIds[idx], windowIds[idx - 1] = windowIds[idx - 1], windowIds[idx]
                    self.arrange()
            elif destination[0] == 's':
                if idx < (len(windowIds) - 2):
                    windowIds[idx], windowIds[idx + 1] = windowIds[idx + 1], windowIds[idx]
                    self.arrange()
        elif dl.isEven():
            # TODO: fix problems when number of columns vary (len(windowIds) % (columns * rows) != 0)
            x = self.windowIdToProperties_[windowId]['frame']['x']
            y = self.windowIdToProperties_[windowId]['frame']['y']
            if destination[0] == 'w':
                swapIdx = idx - 1
                swapId = windowIds[swapIdx]
                #print('w', idx, windowId, swapIdx, swapId, x, self.windowIdToProperties_[swapId]['frame']['x'], y, self.windowIdToProperties_[swapId]['frame']['y'])
                if swapIdx >= 0 and x > self.windowIdToProperties_[swapId]['frame']['x'] and y == self.windowIdToProperties_[swapId]['frame']['y']:
                    windowIds[idx], windowIds[idx - 1] = windowIds[idx - 1], windowIds[idx]
                    self.arrange()
            elif destination[0] == 'e':
                swapIdx = idx + 1
                swapId = windowIds[swapIdx]
                if idx < (len(windowIds) - 1) and x < self.windowIdToProperties_[swapId]['frame']['x'] and y == self.windowIdToProperties_[swapId]['frame']['y']:
                    windowIds[idx], windowIds[swapIdx] = windowIds[swapIdx], windowIds[idx]
                    self.arrange()
            elif destination[0] == 'n':
                for swapIdx  in range(idx - 1, -1, -1):
                    swapId = windowIds[swapIdx]
                    if self.windowIdToProperties_[swapId]['frame']['y'] < y and x == self.windowIdToProperties_[swapId]['frame']['x']:
                        windowIds[idx], windowIds[swapIdx] = windowIds[swapIdx], windowIds[idx]
                        self.arrange()
                        break
            elif destination[0] == 's':
                for swapIdx  in range(idx + 1, len(windowIds)):
                    swapId = windowIds[swapIdx]
                    if y < self.windowIdToProperties_[swapId]['frame']['y'] and x == self.windowIdToProperties_[swapId]['frame']['x']:
                        windowIds[idx], windowIds[swapIdx] = windowIds[swapIdx], windowIds[idx]
                        self.arrange()
                        break

    def moveFocusedWindow(self, destination):
        self.moveWindow(self.focusWindowId_, destination)

    def sizeAndPositionWindow(self, windowId, positionAndSize):
        if positionAndSize[0] == 'f':
            self.__grid(windowId, f'1:1:0:0:1:1')
        elif positionAndSize[0] == 'l':
            self.__grid(windowId, f'1:2:0:0:1:1')
        elif positionAndSize[0] == 'r':
            self.__grid(windowId, f'1:2:1:0:1:1')
        elif positionAndSize[0] == 't':
            self.__grid(windowId, f'2:1:0:0:1:1')
        elif positionAndSize[0] == 'b':
            self.__grid(windowId, f'2:1:0:1:1:1')

    def sizeAndPositionFocusedWindow(self, positionAndSize):
        self.sizeAndPositionWindow(self.focusWindowId_, positionAndSize)

    def windowCreated(self, windowId):
        #print(windowId, type(windowId), self.spaceIdxToWindowIds_[self.focusSpaceIdx_])
        if windowId in self.spaceIdxToWindowIds_[self.focusSpaceIdx_]:
            #print('removed:', windowId)
            self.spaceIdxToWindowIds_[self.focusSpaceIdx_].remove(windowId)
        self.spaceIdxToWindowIds_[self.focusSpaceIdx_].append(windowId)
        #print(len(self.spaceIdxToWindowIds_[self.focusSpaceIdx_]))
        self.arrange()

def percentOrPercentAdjustment(value):
    firstChar = value[0]
    if firstChar == '+' or firstChar == '-':
        percent = int(value[1:])
    else:
        percent = int(value)
    if percent < -100 or percent > 100:
        raise ValueError
    return value

def main():
    yq = yabaiQuick()

    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--arrange', help='arrange windows according to current layout', action='store_true')
    parser.add_argument('-ad', '--arrange_desktop', help='arrange windows according to current layout in specified desktop', choices=[str(id + 1) for id in range(len(yq.spaces_))])
    parser.add_argument('-d', '--debug', help='debug mode', action='store_true')
    parser.add_argument('-f', '--focus', help='change focus window', choices=['n', 'next', 'p', 'prev'])
    parser.add_argument('-l', '--layout', help='layout windows with: left(main), right(main), columns, even, disabled', choices=['l', 'left', 'r', 'right', 'c', 'columns', 'd', 'disabled', 'e', 'even'])
    parser.add_argument('-m', '--move', help='move focused window: west, east, north, south', choices=['w', 'west', 'e', 'east', 'n', 'north', 's', 'south'])
    parser.add_argument('-p', '--percent', help='percent that main window occupies (only useful for left and right layouts) (prefix with \'+\' or \'-\' to adjust from current value)', type=percentOrPercentAdjustment)
    parser.add_argument('-s', '--size', help='size (and position) window quickly: full(screen), left(half), right(half), top(half), bottom(half) (Note: "full(screen)" is not the same as MacOS Fullscreen, but rather "whole" screen, but still a normal window.)', choices=['f', 'full', 'l', 'left', 'r', 'right', 't', 'top', 'b', 'bottom'])
    parser.add_argument('-wc', '--window_created', help='window created: pass window id and arrange based on new window.', type=int)
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.arrange:
        yq.arrange()
    elif args.arrange_desktop:
        yq.arrangeSpaceIdx(int(args.arrange_desktop))
    elif args.focus is not None:
        yq.setFocus(args.focus[0] == 'n')
    elif args.layout is not None:
        yq.setLayout(args.layout)
    elif args.move is not None:
        yq.moveFocusedWindow(args.move)
    elif args.percent is not None:
        yq.setPercent(args.percent)
    elif args.size is not None:
        yq.sizeAndPositionFocusedWindow(args.size)
    elif args.window_created is not None:
        yq.windowCreated(args.window_created)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
