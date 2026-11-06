/** 中栏结果表格（FR-4）。 */
import { Table, Typography } from 'antd'
import type { QueryResult } from '../api/types'
import { buildTableColumns, rowsToDataSource } from '../utils/chartOption'

export default function ResultTable({ result }: { result: QueryResult }) {
  return (
    <div style={{ marginTop: 8 }}>
      <Table
        size="small"
        columns={buildTableColumns(result.columns)}
        dataSource={rowsToDataSource(result)}
        rowKey="_key"
        pagination={false}
        scroll={{ x: 'max-content' }}
      />
      {result.truncated && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          结果已截断，仅显示前 {result.rows.length} 行
        </Typography.Text>
      )}
    </div>
  )
}
