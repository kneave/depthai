import {Button, Col, Input, Row, Select, Slider, Switch, Typography} from "antd";
import {QuestionCircleOutlined} from "@ant-design/icons";
import {useSelector} from "react-redux";

function CameraProperties() {
  const config = useSelector((state) => state.demo.config).camera || {}
  const color = config.color || {}
  const mono = config.mono || {}

  return (
    <>
      <div className="title-section">
        <Typography.Title level={2}>Camera Properties</Typography.Title>
      </div>
      <div className="options-section">
        <a href="#" className="info-indicator"><QuestionCircleOutlined/></a>
        <Row className="input-box" gutter={16}>
          <Col span={12}>
            <Typography.Title level={3}>Color</Typography.Title>
            <Input addonBefore="FPS" defaultValue={color.fps}/>
              <span>Resolution</span>
              <Select value={color.resolution}>
                <Select.Option value="1080">THE_1080_P</Select.Option>
                <Select.Option value="2160">THE_4K</Select.Option>
                <Select.Option value="3040">THE_13MP</Select.Option>
              </Select>
          </Col>
          <Col className="column-grid" span={12}>
            <Typography.Title level={3}>Left + Right</Typography.Title>
            <Input addonBefore="FPS" defaultValue="30"/>
            <span>Resolution</span>
            <Select value={mono.resolution}>
              <Select.Option value="400">THE_400_P</Select.Option>
              <Select.Option value="720">THE_720_P</Select.Option>
              <Select.Option value="800">THE_800_P</Select.Option>
            </Select>
          </Col>
        </Row>
        <div className="switchable-option"><Switch/> <span>Enable sync</span></div>
      </div>
      <div className="options-section">
        <a href="#" className="info-indicator"><QuestionCircleOutlined/></a>
        <Row className="input-box">
          <Col span={12}>
            <Col className="gutter-row" span={6}>
              <Input addonBefore="ISO" value={color.iso}/>
            </Col>
            <Col className="gutter-row" span={6}>
              <Input addonBefore="Exposure" value={color.exposure}/>
            </Col>
            <div>
              <span>Saturation</span>
              <Slider marks={{0: '0', 10: '10'}} min={0} max={10} value={color.saturation}/>
            </div>
            <div>
              <span>Contrast</span>
              <Slider marks={{0: '0', 10: '10'}} min={0} max={10} value={color.contrast}/>
            </div>
            <div>
              <span>Brightness</span>
              <Slider marks={{0: '0', 10: '10'}} min={0} max={10} value={color.brightness}/>
            </div>
            <div>
              <span>Sharpness</span>
              <Slider marks={{0: '0', 4: '4'}} min={0} max={4} value={color.sharpness}/>
            </div>
          </Col>
          <Col span={12}>
            <Input addonBefore="ISO" value={mono.iso}/>
            <Input addonBefore="Exposure" value={mono.exposure}/>
            <div>
              <span>Saturation</span>
              <Slider marks={{0: '0', 10: '10'}} min={0} max={10} value={color.saturation}/>
            </div>
            <div>
              <span>Contrast</span>
              <Slider marks={{0: '0', 10: '10'}} min={0} max={10} value={color.contrast}/>
            </div>
            <div>
              <span>Brightness</span>
              <Slider marks={{0: '0', 10: '10'}} min={0} max={10} value={color.brightness}/>
            </div>
            <div>
              <span>Sharpness</span>
              <Slider marks={{0: '0', 4: '4'}} min={0} max={4} value={color.sharpness}/>
            </div>
          </Col>
        </Row>
      </div>
      <Button className="restart-button" type="primary" block size="large">
        Apply and Restart
      </Button>
    </>
  );
}

export default CameraProperties;
